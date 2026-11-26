from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict

type Motif = Literal["split_element_high8_low24", "read_zero_and_size_dependent_index"]


class OperandObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    function: str
    fields: dict[str, Motif | None]


def resolve_permutation(
    field_mapping: dict[str, str],
    reference: OperandObservation,
    observed: OperandObservation,
) -> dict[str, str]:
    reference_counts = Counter(reference.fields.values())
    observed_counts = Counter(observed.fields.values())
    observed_by_motif = {motif: field for field, motif in observed.fields.items() if motif is not None}
    forced = {
        observed_by_motif[motif]: field
        for field, motif in reference.fields.items()
        if motif is not None and reference_counts[motif] == observed_counts[motif] == 1
    }
    if not forced:
        return {}

    mapping = {obf: field for obf, field in field_mapping.items() if obf in observed.fields}
    if mapping.keys() != observed.fields.keys() or set(mapping.values()) != reference.fields.keys():
        return {}

    assigned_fields = set(forced.values())
    remaining = {
        obf: field for obf, field in mapping.items()
        if obf not in forced and field not in assigned_fields
    }
    unassigned_obf = mapping.keys() - forced.keys() - remaining.keys()
    unassigned_fields = set(mapping.values()) - assigned_fields - set(remaining.values())
    if len(unassigned_obf) == len(unassigned_fields) == 1:
        remaining[next(iter(unassigned_obf))] = next(iter(unassigned_fields))
    elif unassigned_obf or unassigned_fields:
        return {}
    return {obf: field for obf, field in (remaining | forced).items() if mapping[obf] != field}
