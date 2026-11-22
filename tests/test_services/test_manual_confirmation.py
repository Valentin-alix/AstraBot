import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from ankama_launcher_emulator.interfaces.mail_account import ImapAccountConfig, ManualAccountConfig, SmailProAccountConfig
from ankama_launcher_emulator.web._client.mail_providers import config as mail_config
from ankama_launcher_emulator.web._client.mail_providers.manual import ManualCodeInput
from src.services.manual_confirmation import ManualConfirmationBroker, manual_confirmation


def test_requests_are_correlated_and_expiration_and_shutdown_release_waiters() -> None:
    async def scenario() -> None:
        broker = ManualConfirmationBroker()
        requests: list[str] = []
        broker.install(lambda request: requests.append(request.identifier), lambda _: None)
        first = asyncio.create_task(broker.wait("first@example.com", 10))
        second = asyncio.create_task(broker.wait("second@example.com", 10))
        await asyncio.sleep(0)
        with pytest.raises(ValueError):
            broker.submit(requests[0], "123")
        broker.submit(requests[1], "654321")
        assert await second == "654321"
        assert not first.done()
        broker.shutdown()
        assert await first is None
        broker.install(lambda request: requests.append(request.identifier), lambda _: None)
        assert await broker.wait("expired@example.com", 0.001) is None
        assert not broker.is_pending(requests[-1])
        broker.submit(requests[-1], "111111")

    asyncio.run(scenario())


@pytest.mark.parametrize("config", [None, ManualAccountConfig()])
def test_manual_provider_submits_code_through_broker(config: ManualAccountConfig | None) -> None:
    async def scenario() -> None:
        identifiers: list[str] = []
        manual_confirmation.install(lambda request: identifiers.append(request.identifier), lambda _: None)
        with patch.object(mail_config.MailAccountController, "get_config", return_value=config):
            provider = mail_config.resolve_mail_provider("mail@example.com")
        task = asyncio.create_task(provider.wait_for_code(since=datetime.now(UTC), timeout_seconds=5))
        await asyncio.sleep(0)
        manual_confirmation.submit(identifiers[0], "123456")
        assert await task == "123456"

    try:
        asyncio.run(scenario())
    finally:
        manual_confirmation.shutdown()


@pytest.mark.parametrize(
    "config",
    [
        ImapAccountConfig(host="imap.example.com", username="user", password="password"),
        SmailProAccountConfig(email="mail@example.com", api_key="key", timestamp=0),
    ],
)
def test_automatic_provider_times_out_without_prompt(config: ImapAccountConfig | SmailProAccountConfig) -> None:
    requests: list[str] = []
    manual_confirmation.install(lambda request: requests.append(request.identifier), lambda _: None)
    try:
        with (
            patch.object(mail_config.MailAccountController, "get_config", return_value=config),
            patch.object(ManualCodeInput, "start") as start_terminal,
        ):
            provider = mail_config.resolve_mail_provider("mail@example.com")
            assert asyncio.run(provider.wait_for_code(since=datetime.now(UTC), timeout_seconds=0)) is None
            start_terminal.assert_not_called()
        assert requests == []
    finally:
        manual_confirmation.shutdown()
