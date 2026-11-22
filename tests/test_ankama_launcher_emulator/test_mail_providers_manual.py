from datetime import UTC, datetime
from io import StringIO
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from ankama_launcher_emulator.web._client.mail_providers import (
    manual as manual_module,
)
from ankama_launcher_emulator.web._client.mail_providers.manual import (
    ManualCodeInput,
    ManualMailCodeProvider,
)

class TestManualCodeInput(TestCase):
    def test_read_loop_queues_codes_and_ignores_other_lines(self) -> None:
        manual = ManualCodeInput()

        with patch.object(manual_module.sys, "stdin", StringIO("hello\n\n123456\n")):
            manual._read_loop()

        self.assertEqual(manual.poll(), "123456")
        self.assertIsNone(manual.poll())
        self.assertTrue(manual._closed)

    def test_start_returns_none_when_stdin_is_not_a_terminal(self) -> None:
        with patch.object(manual_module.sys, "stdin", StringIO("123456\n")):
            self.assertIsNone(ManualCodeInput.start())


class _StubManualCodeInput:
    def __init__(self, code: str) -> None:
        self._code = code
        self.drained = False

    def drain(self) -> None:
        self.drained = True

    def poll(self) -> str | None:
        return self._code


class TestManualMailCodeProvider(IsolatedAsyncioTestCase):
    async def test_returns_code_typed_in_terminal(self) -> None:
        manual = _StubManualCodeInput("654321")
        provider = ManualMailCodeProvider("mail@example.com")

        with patch.object(manual_module.ManualCodeInput, "start", return_value=manual):
            code = await provider.wait_for_code(
                since=datetime(2026, 6, 18, 10, 0, tzinfo=UTC), timeout_seconds=5
            )

        self.assertEqual(code, "654321")
        self.assertTrue(manual.drained)
