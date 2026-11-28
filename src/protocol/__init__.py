from threading import Lock
lazy from DBDofusUnity.consts import PROTOS_ROOT
lazy from src.utils.registry import import_proto_modules

_initialization_lock = Lock()
_initialized = False


def initialize_protocol() -> None:
    global _initialized
    if _initialized:
        return
    with _initialization_lock:
        if _initialized:
            return
        for folder in ("obf/game", "non_obf/game", "non_obf/connection"):
            import_proto_modules(str(PROTOS_ROOT / folder))
        _initialized = True
