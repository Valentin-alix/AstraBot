from DBDofusUnity.proto_mapper_assembly.interfaces.assembly_access import (
    AccessAtomKey,
    AccessAtomSequenceKey,
    FieldAccessSignatures,
    FunctionSimilarityKey,
)
from DBDofusUnity.proto_mapper_assembly.interfaces.dump_cs_message import DeclaredFieldShape, DumpCSMessageField
from DBDofusUnity.proto_mapper_assembly.interfaces.field_category import FieldTypeShape
from DBDofusUnity.proto_mapper_assembly.interfaces.field_comparison import FieldComparisonKey
from DBDofusUnity.proto_mapper_assembly.scoring.primitives import ratio_similarity
from utils.cache import cache


def function_similarity_from_keys(left: FunctionSimilarityKey, right: FunctionSimilarityKey) -> float:
    if left.return_role != right.return_role or left.takes_message_parameter != right.takes_message_parameter:
        return 0.0

    return (
        0.95 * access_atom_sequence_similarity(left.self_accesses, right.self_accesses)
        + 0.05 * ratio_similarity(left.size, right.size, max_value=max(left.size, right.size))
    )


@cache
def access_atom_sequence_similarity(left: AccessAtomSequenceKey, right: AccessAtomSequenceKey) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0

    shared_length = min(len(left), len(right))
    total_similarity = sum(
        _access_atom_similarity_from_keys(left_access, right_access)
        for left_access, right_access in zip(left[:shared_length], right[:shared_length], strict=True)
    )
    return total_similarity / max(len(left), len(right))


@cache
def _access_atom_similarity_from_keys(left: AccessAtomKey, right: AccessAtomKey) -> float:
    """Compare access order and relative positions; ignore field offsets that drift across builds."""
    if left.entry_type != right.entry_type:
        return 0.0

    if left.field_type_shape != right.field_type_shape:
        return 0.0

    if left.access_kind != right.access_kind:
        return 0.0

    score = ratio_similarity(
        left.index_in_function,
        right.index_in_function,
        max_value=max(left.index_in_function, right.index_in_function),
    )
    return _blend_comparisons(score, left.comparisons, right.comparisons)


def _blend_comparisons(
    score: float,
    left: tuple[FieldComparisonKey, ...],
    right: tuple[FieldComparisonKey, ...],
) -> float:
    if not left or not right:
        return score
    left_set, right_set = set(left), set(right)
    return 0.9 * score + 0.1 * len(left_set & right_set) / len(left_set | right_set)


@cache
def field_access_multiset_similarity(left: AccessAtomSequenceKey, right: AccessAtomSequenceKey) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0

    left_by_kind: dict[tuple[str, FieldTypeShape | None, str], list[AccessAtomKey]] = {}
    right_by_kind: dict[tuple[str, FieldTypeShape | None, str], list[AccessAtomKey]] = {}
    for accesses, grouped in ((left, left_by_kind), (right, right_by_kind)):
        for access in accesses:
            key = (access.entry_type, access.field_type_shape, access.access_kind)
            grouped.setdefault(key, []).append(access)

    total_similarity = 0.0
    for key, left_accesses in left_by_kind.items():
        right_accesses = right_by_kind.get(key)
        if right_accesses is None:
            continue
        left_group = sorted(left_accesses, key=lambda access: access.index_in_function)
        right_group = sorted(right_accesses, key=lambda access: access.index_in_function)
        shared_length = min(len(left_group), len(right_group))
        total_similarity += sum(
            _access_atom_similarity_from_keys(left_access, right_access)
            for left_access, right_access in zip(
                left_group[:shared_length], right_group[:shared_length], strict=True
            )
        )

    return total_similarity / max(len(left), len(right))


@cache
def field_signature_similarity(left: FieldAccessSignatures, right: FieldAccessSignatures) -> float:
    if left.field_type_shape != right.field_type_shape:
        return 0
    return field_access_multiset_similarity(left.accesses_key, right.accesses_key)


_UNTRACED_FIELD_SIMILARITY = 0.65


def field_evidence_similarity(left: FieldAccessSignatures, right: FieldAccessSignatures) -> float:
    """Missing traces are neutral; traced empty getter signatures still contradict populated ones."""
    if left.field_type_shape != right.field_type_shape:
        return 0
    if left.is_traced and right.is_traced:
        return field_signature_similarity(left, right)
    if not left.accesses_key and not right.accesses_key:
        return 1.0
    return _UNTRACED_FIELD_SIMILARITY


_NUMERIC_KIND_MISMATCH_SIMILARITY = 0.5


def declared_field_similarity(left: DumpCSMessageField, right: DumpCSMessageField) -> float:
    return declared_field_shape_similarity(left.declared_field_shape, right.declared_field_shape)


def declared_field_shape_similarity(left: DeclaredFieldShape, right: DeclaredFieldShape) -> float:
    if left.field_type != right.field_type or left.in_oneof != right.in_oneof:
        return 0.0
    left_kind, right_kind = left.numeric_kind, right.numeric_kind
    if left_kind is None or right_kind is None or left_kind == right_kind:
        return 1.0
    return _NUMERIC_KIND_MISMATCH_SIMILARITY
