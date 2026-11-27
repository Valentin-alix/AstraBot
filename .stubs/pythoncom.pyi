COINIT_APARTMENTTHREADED: int

class com_error(Exception):
    hresult: int

def CoInitializeEx(flags: int) -> None: ...
def CoUninitialize() -> None: ...
