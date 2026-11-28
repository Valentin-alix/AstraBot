"""Replay archived builds and score recovery against each archive's pinned message and field pairs."""

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Iterator, Mapping
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass
from functools import cached_property
from multiprocessing import get_context
from pathlib import Path
from time import perf_counter

sys.path.append(str(Path(__file__).parents[3]))

from DBDofusUnity.consts import (
    OBF_GAME_SNAPSHOTS_DIR,
    PINNED_PAIRS_FILE,
)
from DBDofusUnity.proto_mapper_assembly.controllers.game_mappings import (
    build_game_mappings_document,
)
from DBDofusUnity.proto_mapper_assembly.controllers.matching_inputs_loader import (
    NonObfMatchingInputs,
    load_matching_inputs_for_obf_build,
    load_non_obf_matching_inputs,
)
from DBDofusUnity.proto_mapper_assembly.controllers.message_lookup import (
    build_non_obf_alias_lookup,
    build_obf_alias_lookup,
    resolve_non_obf_alias,
    resolve_obf_alias,
)
from DBDofusUnity.proto_mapper_assembly.controllers.pinned_pairs import (
    load_pinned_pairs,
)
from DBDofusUnity.proto_mapper_assembly.helpers.archived_builds import (
    PROTO_ACCESSES_RELATIVE_PATH,
    PROTOCOL_GAME_DUMP_CS_RELATIVE_PATH,
    iter_archived_build_dirs,
)
from DBDofusUnity.proto_mapper_assembly.interfaces.capture_sequence_hints import CaptureSequenceHintsConfig
from DBDofusUnity.proto_mapper_assembly.interfaces.dump_cs_message import DumpCSMessage
from DBDofusUnity.proto_mapper_assembly.interfaces.game_mappings import (
    GameMappingEntry,
    GameMappingsDocument,
)
from DBDofusUnity.proto_mapper_assembly.interfaces.matching_inputs import MatchingRunConfig
from DBDofusUnity.proto_mapper_assembly.interfaces.pinned_pairs import PinnedPair, PinnedPairsConfig
from DBDofusUnity.proto_mapper_assembly.interfaces.runtime_data import RuntimeRoot
from DBDofusUnity.proto_mapper_assembly.matching.orchestrator import match_messages
from DBDofusUnity.proto_mapper_assembly.runtime.runtime_store import RuntimeDataStore


class _EmptyRuntimeDataStore(RuntimeDataStore):
    @cached_property
    def content_by_name(self) -> RuntimeRoot:
        return RuntimeRoot(root={})


@dataclass(frozen=True)
class EraReplay:
    build_id: str
    pin_outcomes: tuple["PinOutcome", ...]
    field_outcomes: tuple["FieldOutcome", ...]
    excluded_pin_count: int
    elapsed_seconds: float


def main() -> None:
    started = perf_counter()
    parser = _build_argument_parser()
    arguments = parser.parse_args()
    if arguments.jobs < 1:
        parser.error("--jobs must be positive")
    build_dirs = _resolve_build_dirs(snapshots_root=arguments.snapshots_root, requested=arguments.builds)
    if not build_dirs:
        raise SystemExit("no archived build with an obf dump, an obf trace and pinned_pairs.json")

    print(f"replaying {len(build_dirs)} builds\n")

    replays_by_build = dict(_compute_replays(build_dirs, jobs=arguments.jobs))
    replays = [replays_by_build[build_dir] for build_dir in build_dirs]
    _print_report(replays)
    print(f"\nTotal wall time {perf_counter() - started:.2f}s")
    if arguments.json is not None:
        arguments.json.write_text(
            json.dumps({"replays": [asdict(replay) for replay in replays]}, indent=2) + "\n",
            encoding="utf-8",
        )


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--snapshots-root",
        type=Path,
        default=OBF_GAME_SNAPSHOTS_DIR,
        help="Directory holding one sub-directory per archived build.",
    )
    parser.add_argument(
        "--builds",
        nargs="*",
        default=None,
        help="Restrict to these build directory names, newest first. Defaults to every usable one.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Write outcomes, field identities and duration as JSON.",
    )
    parser.add_argument("--jobs", type=int, default=4, help="Number of replay processes (default: %(default)s).")
    return parser


def _compute_replays(build_dirs: list[Path], *, jobs: int) -> Iterator[tuple[Path, EraReplay]]:
    if not build_dirs:
        return
    if jobs == 1 or len(build_dirs) == 1:
        non_obf = load_non_obf_matching_inputs(signature_overrides_path=None)
        for build_dir in build_dirs:
            print(f"--- {build_dir.name}", flush=True)
            yield build_dir, _replay_era(build_dir, non_obf)
        return

    with ProcessPoolExecutor(
        max_workers=min(jobs, len(build_dirs), 61),
        mp_context=get_context("spawn"),
        initializer=_initialize_worker,
    ) as executor:
        futures = {executor.submit(_replay_in_worker, build_dir): build_dir for build_dir in build_dirs}
        for future in as_completed(futures):
            build_dir = futures[future]
            try:
                replay = future.result()
            except Exception as error:
                for pending in futures:
                    pending.cancel()
                raise RuntimeError(f"Replay failed for {build_dir.name}") from error
            print(f"--- {build_dir.name} ({replay.elapsed_seconds:.2f}s)", flush=True)
            yield build_dir, replay


_worker_reference: NonObfMatchingInputs | None = None


def _initialize_worker() -> None:
    global _worker_reference
    _worker_reference = load_non_obf_matching_inputs(signature_overrides_path=None)


def _replay_in_worker(build_dir: Path) -> EraReplay:
    assert _worker_reference is not None
    with open(os.devnull, "w", encoding="utf-8") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
        return _replay_era(build_dir, _worker_reference)


def _resolve_build_dirs(*, snapshots_root: Path, requested: list[str] | None) -> list[Path]:
    usable = iter_archived_build_dirs(
        snapshots_root=snapshots_root,
        required_files=(
            PROTOCOL_GAME_DUMP_CS_RELATIVE_PATH,
            PROTO_ACCESSES_RELATIVE_PATH,
            Path(PINNED_PAIRS_FILE.name),
        ),
    )
    if requested is None:
        return usable
    requested_names = set(requested)
    missing = requested_names.difference(build_dir.name for build_dir in usable)
    if missing:
        raise ValueError(f"Requested builds missing a dump, trace or pin file: {sorted(missing)}")
    return [build_dir for build_dir in usable if build_dir.name in requested_names]


def _replay_era(build_dir: Path, non_obf: NonObfMatchingInputs) -> EraReplay:
    started = perf_counter()
    matching_inputs = load_matching_inputs_for_obf_build(
        obf_dump_cs_path=build_dir / PROTOCOL_GAME_DUMP_CS_RELATIVE_PATH,
        obf_proto_accesses_path=build_dir / PROTO_ACCESSES_RELATIVE_PATH,
        non_obf=non_obf,
    )
    non_obf_messages_by_cls = matching_inputs.non_obf_messages_by_cls

    pins = load_pinned_pairs(build_dir / PINNED_PAIRS_FILE.name)
    era_pins = _resolve_era_pins(
        pinned_pairs=pins,
        obf_messages_by_cls=matching_inputs.obf_messages_by_cls,
        non_obf_messages_by_cls=non_obf_messages_by_cls,
    )
    capture_sequence_hints = CaptureSequenceHintsConfig(sequences=())

    matches = match_messages(
        inputs=matching_inputs,
        run_config=MatchingRunConfig(
            runtime_data_store=_EmptyRuntimeDataStore(),
            pinned_pairs_config=PinnedPairsConfig(pairs=[]),
            capture_sequence_hints_config=capture_sequence_hints,
        ),
    )
    candidate_document = build_game_mappings_document(
        matches,
        obf_messages_by_cls=matching_inputs.obf_messages_by_cls,
        non_obf_messages_by_cls=non_obf_messages_by_cls,
    )
    return EraReplay(
        build_id=build_dir.name,
        pin_outcomes=tuple(_score_pins(candidate_document_root=candidate_document.root, era_pins=era_pins)),
        field_outcomes=_score_pinned_fields(candidate_document=candidate_document, pinned_pairs=era_pins),
        excluded_pin_count=len(pins.pairs) - len(era_pins.pairs),
        elapsed_seconds=perf_counter() - started,
    )


def _resolve_era_pins(
    *,
    pinned_pairs: PinnedPairsConfig,
    obf_messages_by_cls: Mapping[str, DumpCSMessage],
    non_obf_messages_by_cls: Mapping[str, DumpCSMessage],
) -> PinnedPairsConfig:
    """Drop pins for removed messages so historical replay tolerates protocol drift."""
    non_obf_alias_to_cls, short_non_obf_alias_to_cls = build_non_obf_alias_lookup(
        non_obf_messages_by_cls=non_obf_messages_by_cls
    )
    obf_alias_to_cls = build_obf_alias_lookup(obf_messages_by_cls=obf_messages_by_cls)
    resolved_pairs: list[PinnedPair] = []
    for pair in pinned_pairs.pairs:
        try:
            resolved_non_obf = resolve_non_obf_alias(
                pair.non_obf, non_obf_alias_to_cls, short_non_obf_alias_to_cls
            )
            resolved_obf = resolve_obf_alias(pair.obf, obf_alias_to_cls)
        except ValueError:
            continue
        resolved_pairs.append(pair.model_copy(update={"obf": resolved_obf, "non_obf": resolved_non_obf}))
    return PinnedPairsConfig(pairs=resolved_pairs)


def _score_pins(
    *,
    candidate_document_root: Mapping[str, GameMappingEntry],
    era_pins: PinnedPairsConfig,
) -> "list[PinOutcome]":
    key_by_normalized_name = {_normalize_name(key): key for key in candidate_document_root}
    outcomes: list[PinOutcome] = []
    for pinned_pair in era_pins.pairs:
        key = key_by_normalized_name.get(_normalize_name(pinned_pair.non_obf))
        entry = candidate_document_root.get(key) if key is not None else None
        actual_obf = entry.full_obf_msg_namespace if entry is not None else None
        outcomes.append(
            PinOutcome(
                non_obf_key=key or pinned_pair.non_obf,
                expected_obf=pinned_pair.obf,
                actual_obf=actual_obf,
            )
        )
    return outcomes


def _print_report(replays: list[EraReplay]) -> None:
    for replay in replays:
        print(f"\n{replay.build_id} ({replay.elapsed_seconds:.2f}s)")
        print(f"  messages: {_format_outcomes(replay.pin_outcomes)}")
        print(f"  fields: {_format_outcomes(replay.field_outcomes)}")
        print(f"  unresolved pins excluded: {replay.excluded_pin_count}")
    print(
        f"\nTOTAL messages: {_format_outcomes(tuple(p for replay in replays for p in replay.pin_outcomes))}"
    )
    print(f"TOTAL fields: {_format_outcomes(tuple(f for replay in replays for f in replay.field_outcomes))}")


@dataclass(frozen=True)
class PinOutcome:
    non_obf_key: str
    expected_obf: str
    actual_obf: str | None

    @property
    def is_recovered(self) -> bool:
        return self.actual_obf == self.expected_obf

    @property
    def status(self) -> str:
        if self.actual_obf is None:
            return "unmapped"
        return "correct" if self.is_recovered else "wrong"


@dataclass(frozen=True)
class FieldOutcome:
    non_obf_key: str
    field: str
    expected_message: str
    actual_message: str | None
    expected_field: str
    actual_field: str | None

    @property
    def status(self) -> str:
        if self.actual_message is None or self.actual_field is None:
            return "unmapped"
        if (self.expected_message, self.expected_field) == (self.actual_message, self.actual_field):
            return "correct"
        return "wrong"


def _score_pinned_fields(
    *,
    candidate_document: GameMappingsDocument,
    pinned_pairs: PinnedPairsConfig,
) -> tuple[FieldOutcome, ...]:
    candidates = {_normalize_name(key): entry for key, entry in candidate_document.root.items()}
    outcomes: list[FieldOutcome] = []
    for pair in pinned_pairs.pairs:
        if not pair.field_mapping_by_obf:
            continue
        candidate = candidates.get(_normalize_name(pair.non_obf))
        actual_fields = {name: obf for obf, name in candidate.field_mapping.items()} if candidate else {}
        for field, expected_field in pair.field_mapping_by_non_obf.items():
            outcomes.append(
                FieldOutcome(
                    non_obf_key=pair.non_obf,
                    field=field,
                    expected_message=pair.obf,
                    actual_message=candidate.full_obf_msg_namespace if candidate else None,
                    expected_field=expected_field,
                    actual_field=actual_fields.get(field),
                )
            )
    return tuple(outcomes)


def _normalize_name(value: str) -> str:
    return value.removeprefix(".").casefold()


def _format_outcomes(outcomes: tuple[PinOutcome, ...] | tuple[FieldOutcome, ...]) -> str:
    counts = Counter(outcome.status for outcome in outcomes)
    return " | ".join(f"{status}={counts[status]}" for status in ("correct", "wrong", "unmapped"))


if __name__ == "__main__":
    main()
