import functools
import os
import threading
from collections.abc import Callable
from time import perf_counter
from typing import Final, ParamSpec, TypeVar

from src.utils.project_paths import IS_PACKAGED
from src.utils.runtime_support import RuntimeSetupError

P = ParamSpec("P")
R = TypeVar("R")


def _profiling_enabled() -> bool:
    if IS_PACKAGED:
        return False
    value = os.environ.get("PROFILING_ENABLED", "false").lower()
    if value in ("1", "true"):
        return True
    if value in ("0", "false"):
        return False
    raise RuntimeSetupError("The PROFILING_ENABLED variable must be 0, 1, false, or true.")


PROFILING_ENABLED: Final = _profiling_enabled()


def profiled_slot(func: Callable[P, R], threshold_ms: int = 1) -> Callable[P, R]:
    if not PROFILING_ENABLED:
        return func

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            dt = (perf_counter() - start) * 1000
            if dt >= threshold_ms:
                function_name = getattr(func, "__qualname__", type(func).__qualname__)
                print(f"[SLOT] {function_name} | {dt:.2f} ms | {threading.current_thread().name}")

    return wrapper
