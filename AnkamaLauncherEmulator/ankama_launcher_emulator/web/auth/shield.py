import asyncio
import logging
from datetime import UTC, datetime

from ankama_launcher_emulator.haapi.haapi import (
    Haapi,
    ShieldNotRequiredError,
)
from ankama_launcher_emulator.interfaces.credentials import (
    DecipheredCertif,
)
from ankama_launcher_emulator.interfaces.haapi_api import SignOnResponse
from ankama_launcher_emulator.web._client.mail_providers.base import (
    MailboxCodeTimeoutError,
    MailCodeProvider,
)

from ankama_launcher_emulator.web._client.mail_providers.config import snapshot_confirmation_inbox

ZAAP_GAME_ID = 102

logger = logging.getLogger(__name__)


async def _request_and_validate_email_certificate(
    haapi: Haapi,
    mail_provider: MailCodeProvider,
    timeout_seconds: int,
) -> DecipheredCertif:
    await snapshot_confirmation_inbox(mail_provider)
    requested_at = datetime.now(UTC)
    domain = await asyncio.to_thread(haapi.get_security_code, "EMAIL")
    logger.info("[OAuth] Shield security code requested (domain=%s)", domain)

    code = await mail_provider.wait_for_code(
        since=requested_at, timeout_seconds=timeout_seconds
    )
    if code is None:
        raise MailboxCodeTimeoutError(f"Timed out waiting for Shield/OTP code in mailbox for {haapi.login}")

    certif = await asyncio.to_thread(haapi.validate_code, code, ZAAP_GAME_ID)
    logger.info("[OAuth] Certificate obtained (id=%s)", certif.id)
    return certif


async def resolve_shield(
    haapi: Haapi,
    account_info: SignOnResponse | None,
    mail_provider: MailCodeProvider,
    started_at: datetime,
    *,
    timeout_seconds: int = 300,
) -> DecipheredCertif | None:
    security = account_info.security if account_info is not None else []
    has_shield = "SHIELD" in security
    has_otp = "OTP" in security
    if not (has_shield or has_otp):
        return None

    if has_shield:
        return await _request_and_validate_email_certificate(
            haapi, mail_provider, timeout_seconds
        )

    logger.info("[OAuth] OTP required; waiting for code in mailbox...")
    code = await mail_provider.wait_for_code(
        since=started_at, timeout_seconds=timeout_seconds
    )
    if code is None:
        raise MailboxCodeTimeoutError(f"Timed out waiting for Shield/OTP code in mailbox for {haapi.login}")

    certif = await asyncio.to_thread(haapi.validate_otp, code, ZAAP_GAME_ID)
    logger.info("[OAuth] Certificate obtained (id=%s)", certif.id)
    return certif


async def secure_apikey_via_email(
    haapi: Haapi,
    mail_provider: MailCodeProvider,
    *,
    timeout_seconds: int = 300,
) -> DecipheredCertif | None:
    """Secure keys even without a sign-on challenge; NONEEDTOBESECURED permits an unsecured key."""
    logger.info("[OAuth] Securing apikey via forced email Shield flow...")
    try:
        return await _request_and_validate_email_certificate(haapi, mail_provider, timeout_seconds)
    except ShieldNotRequiredError:
        logger.info(
            "[OAuth] Apikey does not need securing (NONEEDTOBESECURED); proceeding without certificate."
        )
        return None
