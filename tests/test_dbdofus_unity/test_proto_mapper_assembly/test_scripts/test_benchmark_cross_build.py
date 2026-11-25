from pathlib import Path
from unittest.mock import PropertyMock, patch

from DBDofusUnity.proto_mapper_assembly.controllers.matching_inputs_loader import NonObfMatchingInputs
from DBDofusUnity.proto_mapper_assembly.interfaces.matching_inputs import MatchingInputs
from DBDofusUnity.proto_mapper_assembly.interfaces.pinned_pairs import PinnedPair, PinnedPairsConfig
from DBDofusUnity.proto_mapper_assembly.runtime.runtime_store import RuntimeDataStore
from scripts.mapping.debug import benchmark_cross_build as benchmark
from tests.fixtures.proto_mapper.message_builders import EMPTY_ACCESS_TRACE
from tests.fixtures.proto_mapper.script_builders import game_mapping_entry


def test_pin_scores_normalize_names_and_keep_pin_names_for_missing_messages() -> None:
    pins = PinnedPairsConfig(
        pairs=[
            PinnedPair(obf="right", non_obf="Protocol.Present"),
            PinnedPair(obf="gone", non_obf="Protocol.Missing"),
            PinnedPair(obf="expected", non_obf="Protocol.Wrong"),
        ]
    )
    candidate = {
        ".protocol.Present": game_mapping_entry(field_mapping={}, obf_cls="right"),
        ".protocol.Wrong": game_mapping_entry(field_mapping={}, obf_cls="actual"),
    }
    outcomes = benchmark._score_pins(
        candidate_document_root=candidate,
        era_pins=pins,
    )
    assert [outcome.non_obf_key for outcome in outcomes] == [
        ".protocol.Present",
        "Protocol.Missing",
        ".protocol.Wrong",
    ]
    assert [outcome.actual_obf for outcome in outcomes] == ["right", None, "actual"]
    assert [outcome.is_recovered for outcome in outcomes] == [True, False, False]


def test_replay_never_accesses_the_production_capture_path(tmp_path: Path) -> None:
    production_store = RuntimeDataStore()
    reference = NonObfMatchingInputs({}, {}, {}, EMPTY_ACCESS_TRACE)
    inputs = MatchingInputs({}, {}, {}, {}, {}, {}, {}, EMPTY_ACCESS_TRACE, EMPTY_ACCESS_TRACE)
    (tmp_path / benchmark.PINNED_PAIRS_FILE.name).write_text('{"pairs":[]}', encoding="utf-8")

    with (
        patch.object(
            RuntimeDataStore, "path", new_callable=PropertyMock, side_effect=AssertionError("capture path")
        ) as capture_path,
        patch.object(benchmark, "load_matching_inputs_for_obf_build", return_value=inputs),
        patch.object(benchmark, "match_messages", wraps=benchmark.match_messages) as match,
    ):
        replay = benchmark._replay_era(tmp_path, reference)

    capture_path.assert_not_called()
    store = match.call_args.kwargs["run_config"].runtime_data_store
    assert store is not production_store
    assert store.content_by_name.root == {}
    assert replay.pin_outcomes == ()
