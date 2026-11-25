from pathlib import Path

from DBDofusUnity.proto_mapper_assembly.interfaces.game_mappings import GameMappingsDocument
from DBDofusUnity.proto_mapper_assembly.interfaces.pinned_pairs import PinnedPair, PinnedPairsConfig
from scripts.mapping.debug import benchmark_cross_build as benchmark
from tests.fixtures.proto_mapper.script_builders import game_mapping_entry


def test_report_scores_only_explicit_message_and_field_pins() -> None:
    pins = PinnedPairsConfig(pairs=[
        PinnedPair(obf="right", non_obf="protocol.Present", field_mapping_by_obf={"x": "value", "y": "missing"}),
        PinnedPair(obf="expected", non_obf="protocol.Wrong", field_mapping_by_obf={"x": "value"}),
        PinnedPair(obf="empty", non_obf="protocol.MessageOnly"),
    ])
    candidate = GameMappingsDocument(root={
        ".protocol.Present": game_mapping_entry(obf_cls="right", field_mapping={"x": "value", "z": "unpinned"}),
        ".protocol.Wrong": game_mapping_entry(obf_cls="wrong", field_mapping={"x": "value"}),
        ".protocol.Unpinned": game_mapping_entry(obf_cls="other", field_mapping={"x": "value"}),
    })

    messages = benchmark._score_pins(candidate_document_root=candidate.root, era_pins=pins)
    fields = benchmark._score_pinned_fields(candidate_document=candidate, pinned_pairs=pins)

    assert {message.non_obf_key.removeprefix("."): message.status for message in messages} == {
        "protocol.MessageOnly": "unmapped",
        "protocol.Present": "correct",
        "protocol.Wrong": "wrong",
    }
    assert [(field.non_obf_key, field.field, field.status) for field in fields] == [
        ("protocol.Present", "value", "correct"),
        ("protocol.Present", "missing", "unmapped"),
        ("protocol.Wrong", "value", "wrong"),
    ]


def test_cross_build_requires_local_pins_and_accepts_an_archive_without_generated_mappings(tmp_path: Path) -> None:
    build = tmp_path / "2026-10-12"
    (build / "cs").mkdir(parents=True)
    for path in (
        Path("GameAssembly.dll"),
        benchmark.PROTOCOL_GAME_DUMP_CS_RELATIVE_PATH,
        benchmark.PROTO_ACCESSES_RELATIVE_PATH,
    ):
        (build / path).touch()

    assert benchmark._resolve_build_dirs(snapshots_root=tmp_path, requested=None) == []

    (build / "pinned_pairs.json").write_text('{"pairs":[]}', encoding="utf-8")
    assert benchmark._resolve_build_dirs(snapshots_root=tmp_path, requested=None) == [build]
