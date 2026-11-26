from DBDofusUnity.proto_mapper_assembly.field_mapping.operand_provenance import OperandObservation, resolve_permutation


def test_operand_permutation_preserves_ambiguous_mappings() -> None:
    mapping = {"a": "scales", "b": "skins", "c": "indexed_colors", "d": "bones_id"}
    reference = OperandObservation(function="reference", fields={
        "indexed_colors": "split_element_high8_low24",
        "scales": "read_zero_and_size_dependent_index",
        "skins": None,
    })
    observed = OperandObservation(function="observed", fields={
        "a": "split_element_high8_low24",
        "b": "read_zero_and_size_dependent_index",
        "c": None,
    })
    assert resolve_permutation(mapping, reference, observed) == {
        "a": "indexed_colors", "b": "scales", "c": "skins",
    }
    assert mapping["a"] == "scales"

    ambiguous = observed.model_copy(update={"fields": {
        "a": "split_element_high8_low24", "b": None, "c": "split_element_high8_low24",
    }})
    assert resolve_permutation(mapping, reference, ambiguous) == {}
