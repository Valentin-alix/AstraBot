import re
from collections import defaultdict

from DBDofusUnity.proto_mapper_assembly.field_mapping.operand_provenance import Motif

_ASSIGNMENT = re.compile(r"\b(?P<name>[av]\d+) = (?P<value>[^;\n]+);", re.ASCII)
_LOCAL = re.compile(r"\b[av]\d+\b", re.ASCII)
_SOURCE = re.compile(r"\*\(_QWORD \*\)\((?P<base>[av]\d+) \+ (?P<offset>\d+)(?:LL)?\)")
_COLOR_SPLIT = re.compile(
    r"\bsub_[\da-fA-F]+\([^;\n]+, HIBYTE\((?P<element>v\d+)\), (?P=element) & 0xFFFFFF(?:u|LL)?[,)]"
)
_COUNT = re.compile(r"\*\(_DWORD \*\)\((?P<list>v\d+) \+ 24(?:LL)?\)")
_SIZE_TEST = re.compile(r"\bif \( (?P<count>v\d+) == 1 \)")


def extract_motifs(code: str, offsets: set[int]) -> dict[int, Motif]:
    definitions: dict[str, list[re.Match[str]]] = defaultdict(list)
    for assignment in _ASSIGNMENT.finditer(code):
        definitions[assignment["name"]].append(assignment)

    def last_definition(name: str, end: int) -> re.Match[str] | None:
        return next((match for match in reversed(definitions[name]) if match.start() < end), None)

    def origins(name: str, end: int, depth: int = 0) -> set[int]:
        if depth >= 12:
            return set()
        definition = last_definition(name, end)
        if definition is None:
            return set()
        value = definition["value"]
        source = _SOURCE.fullmatch(value)
        if source is not None:
            base = source["base"]
            if base == "a1" or {match["value"] for match in definitions[base]} == {"a1"}:
                offset = int(source["offset"])
                return {offset} if offset in offsets else set()
        return {
            offset
            for variable in _LOCAL.findall(value)
            for offset in origins(variable, definition.start(), depth + 1)
        }

    matches: dict[int, set[Motif]] = defaultdict(set)
    for color in _COLOR_SPLIT.finditer(code):
        source = origins(color["element"], color.start())
        if len(source) == 1:
            matches[next(iter(source))].add("split_element_high8_low24")

    for branch in _SIZE_TEST.finditer(code):
        count = last_definition(branch["count"], branch.start())
        if count is None or (count_read := _COUNT.fullmatch(count["value"])) is None:
            continue
        collection = count_read["list"]
        source = origins(collection, count.start())
        if len(source) != 1:
            continue
        tail = code[branch.end():branch.end() + 1200]
        if re.search(rf"\b{branch['count']} != 2\b", tail) is None:
            continue
        zero = set(re.findall(rf"\b(sub_[\da-fA-F]+)\({collection}, 0,", tail))
        indexes = re.findall(rf"\b(sub_[\da-fA-F]+)\({collection}, (v\d+),", tail)
        for callee, index in indexes:
            if callee in zero and re.search(rf"\b{index} = 0;", tail) and re.search(rf"\b{index} = 1;", tail):
                matches[next(iter(source))].add("read_zero_and_size_dependent_index")
                break
    return {offset: next(iter(motifs)) for offset, motifs in matches.items() if len(motifs) == 1}
