import functools
import os
import threading
from collections.abc import Callable
from time import perf_counter
from typing import Final, ParamSpec, TypeVar

from src.utils.project_paths import IS_PACKAGED

P = ParamSpec("P")
R = TypeVar("R")


def _profiling_enabled() -> bool:
    if IS_PACKAGED:
        return False
    return bool(os.environ.get("PROFILING_ENABLED", 0))


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
