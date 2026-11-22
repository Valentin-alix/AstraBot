import asyncio
import logging
import queue
import re
import sys
import threading
import time
from datetime import datetime
from html import unescape


from src.services.manual_confirmation import manual_confirmation

logger = logging.getLogger(__name__)

CONFIRMATION_CODE_PATTERN = re.compile(r"(?<!\d)(\d(?:\s*\d){5})(?!\s*\d)")
MANUAL_CODE_POLL_INTERVAL_SECONDS = 0.2


def extract_confirmation_code(content: str) -> str | None:
    normalized = re.sub(r"<[^>]+>", " ", unescape(content))
    match = CONFIRMATION_CODE_PATTERN.search(normalized)
    if match is None:
        return None
    return re.sub(r"\s+", "", match.group(1))


class ManualCodeInput:
    _instance: "ManualCodeInput | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._codes: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._closed = False

    @classmethod
    def start(cls) -> "ManualCodeInput | None":
        try:
            is_interactive = sys.stdin is not None and sys.stdin.isatty()
        except ValueError:
            is_interactive = False
        if not is_interactive:
            return None
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            instance = cls._instance
        instance._ensure_thread()
        if instance._closed:
            return None
        return instance

    def drain(self) -> None:
        while self.poll() is not None:
            pass

    def poll(self) -> str | None:
        try:
            return self._codes.get_nowait()
        except queue.Empty:
            return None

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._read_loop, name="manual-confirmation-code", daemon=True
            )
            self._thread.start()

    def _read_loop(self) -> None:
        for line in sys.stdin:
            stripped = line.strip()
            if not stripped:
                continue
            code = extract_confirmation_code(stripped)
            if code is None:
                logger.info("[Mailbox] Ignored manual input (expected 6 digits).")
                continue
            self._codes.put(code)
        with self._lock:
            self._closed = True


async def _sleep_until_manual_code(manual: ManualCodeInput | None, seconds: float) -> str | None:
    deadline = time.monotonic() + seconds
    while True:
        if manual is not None:
            code = manual.poll()
            if code is not None:
                logger.info("[Mailbox] Confirmation code entered manually.")
                return code
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        await asyncio.sleep(min(MANUAL_CODE_POLL_INTERVAL_SECONDS, remaining))


class ManualMailCodeProvider:
    def __init__(self, email: str) -> None:
        self._email = email

    async def wait_for_code(self, *, since: datetime, timeout_seconds: int) -> str | None:
        if manual_confirmation.enabled:
            return await manual_confirmation.wait(self._email, timeout_seconds)
        manual = ManualCodeInput.start()
        if manual is not None:
            manual.drain()
            logger.info("[Mailbox] Type your confirmation code (6 digits + Enter).")
        return await _sleep_until_manual_code(manual, timeout_seconds)
