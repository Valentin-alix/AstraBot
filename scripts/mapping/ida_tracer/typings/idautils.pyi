from collections.abc import Iterator

import idaapi

class xref_t:
    frm: int
    to: int
    type: int
    iscode: bool

def Heads(start: int, end: int) -> Iterator[int]: ...  # noqa: N802
def DecodeInstruction(ea: int) -> idaapi.insn_t | None: ...  # noqa: N802
def DataRefsFrom(ea: int) -> Iterator[int]: ...  # noqa: N802
def FuncItems(ea: int) -> Iterator[int]: ...  # noqa: N802
def XrefsTo(ea: int, flags: int = ...) -> Iterator[xref_t]: ...  # noqa: N802
