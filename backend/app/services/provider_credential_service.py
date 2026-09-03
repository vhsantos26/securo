"""Workspace-scoped provider credentials and provider resolution.

Secrets are encrypted at rest and are never returned by this module. A legacy
environment configuration remains a deliberately narrow fallback for existing
connections whose ``provider_credential_id`` is null.
"""
from __future__ import annotations

import base64
import functools
import hashlib
import uuid
from datetime import datetime, timezone
from typing import cast

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.bank_connection import BankConnection
from app.models.workspace_provider_credential import WorkspaceProviderCredential
from app.providers import all_known_providers, get_provider
from app.providers.base import ProviderNotConfiguredError
from app.providers.pluggy import PluggyProvider


_SALT = b"securo-workspace-provider-credentials-v1"


class WorkspaceCredentialUnavailableError(ProviderNotConfiguredError):
    """A pinned workspace credential cannot safely be substituted.

    This is deliberately distinct from a provider simply not being configured
    in the current process. Callers may retain the legacy registry seam for
    that latter case, but must never swap a connection's pinned credentials
    for the process-wide environment credentials.
    """


@functools.lru_cache(maxsize=1)
def _fernet() -> Fernet:
    secret = get_settings().secret_key.get_secret_value().encode("utf-8")
    raw = hashlib.pbkdf2_hmac("sha256", secret, _SALT, iterations=100_000, dklen=32)
    return Fernet(base64.urlsafe_b64encode(raw))


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def _client_id_hint(value: str) -> str:
    return f"…{value[-4:]}" if len(value) > 4 else "••••"


def _environment_pluggy_configured() -> bool:
    settings = get_settings()
    return bool(settings.pluggy_client_id and settings.pluggy_client_secret.get_secret_value())


async def get_active_credential(
    session: AsyncSession, workspace_id: uuid.UUID, provider: str
) -> WorkspaceProviderCredential | None:
    return await session.scalar(
        select(WorkspaceProviderCredential)
        .where(
            WorkspaceProviderCredential.workspace_id == workspace_id,
            WorkspaceProviderCredential.provider == provider,
            WorkspaceProviderCredential.is_active.is_(True),
            WorkspaceProviderCredential.retired_at.is_(None),
        )
        .order_by(WorkspaceProviderCredential.updated_at.desc())
    )


async def get_credential(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    provider: str,
    credential_id: uuid.UUID,
) -> WorkspaceProviderCredential | None:
    return await session.scalar(
        select(WorkspaceProviderCredential).where(
            WorkspaceProviderCredential.id == credential_id,
            WorkspaceProviderCredential.workspace_id == workspace_id,
            WorkspaceProviderCredential.provider == provider,
            WorkspaceProviderCredential.retired_at.is_(None),
        )
    )


async def save_pluggy_credential(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    client_id: str,
    client_secret: str,
) -> WorkspaceProviderCredential:
    """Create a new active Pluggy profile, preserving prior linked profiles."""
    client_id = client_id.strip()
    client_secret = client_secret.strip()
    if not client_id or not client_secret:
        raise ValueError("Pluggy Client ID and Client Secret are required")

    # Validate before persisting. Invalid secrets never enter the database.
    await PluggyProvider(client_id=client_id, client_secret=client_secret).verify_credentials()

    await session.execute(
        update(WorkspaceProviderCredential)
        .where(
            WorkspaceProviderCredential.workspace_id == workspace_id,
            WorkspaceProviderCredential.provider == "pluggy",
            WorkspaceProviderCredential.is_active.is_(True),
            WorkspaceProviderCredential.retired_at.is_(None),
        )
        .values(is_active=False, updated_by_user_id=user_id, updated_at=datetime.now(timezone.utc))
    )
    credential = WorkspaceProviderCredential(
        workspace_id=workspace_id,
        provider="pluggy",
        client_id=client_id,
        client_secret_encrypted=_encrypt(client_secret),
        is_active=True,
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    session.add(credential)
    await session.flush()
    return credential


async def resolve_provider(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    provider: str,
    credential_id: uuid.UUID | None = None,
    prefer_environment_for_legacy: bool = False,
):
    """Return an integration instance configured for this workspace.

    The explicit ID is used by existing connections; an active profile is used
    for a new connect flow. Other providers keep their existing environment
    configuration until they are migrated to this abstraction.
    """
    if provider != "pluggy":
        return get_provider(provider), None

    credential = (
        await get_credential(session, workspace_id, provider, credential_id)
        if credential_id
        else (
            None
            if prefer_environment_for_legacy
            else await get_active_credential(session, workspace_id, provider)
        )
    )
    if credential_id and credential is None:
        raise WorkspaceCredentialUnavailableError(
            "The selected Pluggy credential is unavailable for this workspace."
        )
    if credential:
        secret = _decrypt(credential.client_secret_encrypted)
        if not secret:
            raise WorkspaceCredentialUnavailableError(
                "Pluggy credentials for this workspace can no longer be decrypted. "
                "An owner must configure them again."
            )
        return PluggyProvider(client_id=credential.client_id, client_secret=secret), credential

    if _environment_pluggy_configured():
        return PluggyProvider(), None
    raise ProviderNotConfiguredError(
        "Pluggy is not configured for this workspace. Ask a workspace owner to configure it."
    )


async def integration_status(session: AsyncSession, workspace_id: uuid.UUID) -> dict:
    active = await get_active_credential(session, workspace_id, "pluggy")
    legacy_count = await session.scalar(
        select(func.count()).select_from(BankConnection).where(
            BankConnection.workspace_id == workspace_id,
            BankConnection.provider == "pluggy",
            BankConnection.provider_credential_id.is_(None),
        )
    ) or 0
    if active:
        source = "workspace" if _decrypt(active.client_secret_encrypted) else "unreadable"
        return {
            "provider": "pluggy",
            "configured": source == "workspace",
            "source": source,
            "client_id_hint": _client_id_hint(active.client_id),
            "active_credential_id": active.id,
            "updated_at": active.updated_at,
            "legacy_connection_count": legacy_count,
        }
    if _environment_pluggy_configured():
        return {
            "provider": "pluggy",
            "configured": True,
            "source": "environment",
            "client_id_hint": _client_id_hint(get_settings().pluggy_client_id),
            "active_credential_id": None,
            "updated_at": None,
            "legacy_connection_count": legacy_count,
        }
    return {
        "provider": "pluggy",
        "configured": False,
        "source": "none",
        "client_id_hint": None,
        "active_credential_id": None,
        "updated_at": None,
        "legacy_connection_count": legacy_count,
    }


async def providers_for_workspace(session: AsyncSession, workspace_id: uuid.UUID) -> list[dict]:
    """Overlay workspace Pluggy status on the legacy provider registry."""
    out = all_known_providers()
    status = await integration_status(session, workspace_id)
    for item in out:
        if item["name"] == "pluggy":
            item["configured"] = status["configured"]
    return out


async def adopt_legacy_pluggy_connections(
    session: AsyncSession, workspace_id: uuid.UUID
) -> int:
    """Pin env-backed Pluggy connections to the active workspace profile.

    This is intentionally explicit: the caller has just configured the same
    Pluggy project and is choosing to migrate its own legacy connections.
    """
    active = await get_active_credential(session, workspace_id, "pluggy")
    if not active:
        raise ValueError("Configure Pluggy for this workspace before adopting connections")
    legacy_connections = list((await session.scalars(
        select(BankConnection).where(
            BankConnection.workspace_id == workspace_id,
            BankConnection.provider == "pluggy",
            BankConnection.provider_credential_id.is_(None),
        )
    )).all())
    if not legacy_connections:
        return 0

    # A matching Client ID is not enough: confirm the new profile can actually
    # read every existing Pluggy Item before changing any persistent pointer.
    provider, _ = await resolve_provider(session, workspace_id, "pluggy", active.id)
    try:
        for connection in legacy_connections:
            await provider.get_accounts(connection.credentials or {})
    except Exception as exc:
        raise ValueError(
            "These credentials cannot access every existing Pluggy connection. "
            "Keep the environment configuration or reconnect the affected bank first."
        ) from exc

    result = await session.execute(
        update(BankConnection)
        .where(
            BankConnection.workspace_id == workspace_id,
            BankConnection.provider == "pluggy",
            BankConnection.provider_credential_id.is_(None),
        )
        .values(provider_credential_id=active.id)
    )
    return cast(CursorResult, result).rowcount or 0
