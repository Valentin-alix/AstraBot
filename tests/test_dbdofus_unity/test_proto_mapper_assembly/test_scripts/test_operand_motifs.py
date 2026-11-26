from scripts.mapping.ida_tracer.tracing.operand_motifs import extract_motifs


def test_split_operands_must_come_from_the_same_collection_element() -> None:
    code = """
    v1 = a1;
    v3 = *(_QWORD *)(v1 + 56);
    v4 = sub_100(v3, qword_200);
    v5 = (*(__int64 (__fastcall **)(__int64))v6)(v4);
    sub_300(v2, HIBYTE(v5), v5 & 0xFFFFFF, 0);
    """
    assert extract_motifs(code, {40, 56, 64}) == {56: "split_element_high8_low24"}
    assert extract_motifs(code.replace("v5 &", "v7 &"), {40, 56, 64}) == {}


def test_collection_index_depends_on_its_size() -> None:
    code = """
    v4 = *(_QWORD *)(a1 + 64);
    v5 = *(_DWORD *)(v4 + 24);
    if ( v5 == 1 )
    {
        sub_100(v4, 0, &v6);
        v7 = 0;
    }
    else
    {
        if ( v5 != 2 )
            goto LABEL_1;
        sub_100(v4, 0, &v6);
        v7 = 1;
    }
    sub_100(v4, v7, &v8);
    """
    assert extract_motifs(code, {40, 56, 64}) == {64: "read_zero_and_size_dependent_index"}
    assert extract_motifs(code.replace("v7 = 1;", "v7 = 3;"), {40, 56, 64}) == {}
