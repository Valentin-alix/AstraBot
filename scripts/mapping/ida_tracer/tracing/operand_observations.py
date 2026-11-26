from collections.abc import Iterable, Mapping

import ida_hexrays
import ida_lines
import idaapi
import idautils

from DBDofusUnity.proto_mapper_assembly.field_mapping.operand_provenance import OperandObservation
from DBDofusUnity.proto_mapper_assembly.interfaces.assembly_access import FieldAccessEntry, FunctionAccessInfo
from DBDofusUnity.proto_mapper_assembly.interfaces.dump_cs_message import DumpCSMessage, DumpCSMessageField
from scripts.mapping.ida_tracer.tracing.operand_motifs import extract_motifs


def collect_operand_observations(
    functions: Iterable[FunctionAccessInfo],
    messages: Mapping[str, DumpCSMessage],
    core_addresses: set[int],
) -> dict[str, OperandObservation]:
    fields_by_message = {
        name: {
            field.memory_offset: field
            for field in message.fields
            if field.property_name is not None and field.clr_type in {"RepeatedField<int>", "RepeatedField<Int32>"}
        }
        for name, message in messages.items()
    }
    observed: dict[str, OperandObservation] = {}
    conflicts: set[str] = set()
    scanned: set[tuple[str, int]] = set()
    for function in functions:
        if len(function.parameters) != 1:
            continue
        candidates = [
            (name, fields_by_message[name])
            for name, accesses in function.accesses_by_cls.items()
            if len(fields_by_message.get(name, {})) >= 2
            and function.parameters[0] in {name, messages[name].name}
            and fields_by_message[name].keys() <= {
                access.field_offset for access in accesses if isinstance(access, FieldAccessEntry)
            }
        ]
        if len(candidates) != 1:
            continue
        name, fields = candidates[0]
        key = (name, function.start_address)
        if key in scanned or not _has_core_caller(function.start_address, core_addresses):
            continue
        scanned.add(key)
        observation = _decompile_observation(function.start_address, fields)
        if observation is None:
            continue
        if name in observed and observed[name].fields != observation.fields:
            conflicts.add(name)
        else:
            observed[name] = observation
    return {name.removeprefix(".").casefold(): value for name, value in observed.items() if name not in conflicts}


def _has_core_caller(address: int, core_addresses: set[int]) -> bool:
    return any(
        caller.start_ea != address and caller.start_ea in core_addresses
        for xref in idautils.XrefsTo(address)
        if xref.iscode and (caller := idaapi.get_func(xref.frm)) is not None
    )


def _decompile_observation(address: int, fields: dict[int, DumpCSMessageField]) -> OperandObservation | None:
    try:
        function = ida_hexrays.decompile(address)
    except ida_hexrays.DecompilationFailure:
        return None
    if function is None:
        return None
    code = "\n".join(ida_lines.tag_remove(line.line) for line in function.get_pseudocode())
    motifs = extract_motifs(code, set(fields))
    if not motifs:
        return None
    return OperandObservation(
        function=f"{address:#x}",
        fields={field.clean_field_name: motifs.get(offset) for offset, field in fields.items()},
    )
