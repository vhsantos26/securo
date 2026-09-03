import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.bank_connection import BankConnection
from app.providers.base import ProviderNotConfiguredError
from app.services.connection_service import _resolve_provider_for_workspace
from app.services import provider_credential_service as service


@pytest.mark.asyncio
async def test_workspace_credential_is_encrypted_and_status_is_redacted(
    session, test_user, test_workspace
):
    with patch("app.providers.pluggy.PluggyProvider.verify_credentials", new_callable=AsyncMock):
        credential = await service.save_pluggy_credential(
            session, test_workspace.id, test_user.id, "client-123456", "secret-value"
        )
    await session.commit()

    assert credential.client_secret_encrypted != "secret-value"
    status = await service.integration_status(session, test_workspace.id)
    assert status["configured"] is True
    assert status["source"] == "workspace"
    assert status["client_id_hint"] == "…3456"
    assert "secret" not in status


@pytest.mark.asyncio
async def test_rotating_active_profile_does_not_change_existing_connection(
    session, test_user, test_workspace
):
    with patch("app.providers.pluggy.PluggyProvider.verify_credentials", new_callable=AsyncMock):
        original = await service.save_pluggy_credential(
            session, test_workspace.id, test_user.id, "client-old", "secret-old"
        )
        connection = BankConnection(
            workspace_id=test_workspace.id,
            user_id=test_user.id,
            provider="pluggy",
            provider_credential_id=original.id,
            external_id="item-old",
            institution_name="Bank",
            credentials={"item_id": "item-old"},
        )
        session.add(connection)
        await session.flush()
        replacement = await service.save_pluggy_credential(
            session, test_workspace.id, test_user.id, "client-new", "secret-new"
        )
    await session.commit()

    provider, resolved = await service.resolve_provider(
        session, test_workspace.id, "pluggy", connection.provider_credential_id
    )
    assert resolved is not None and resolved.id == original.id
    assert provider._client_id == "client-old"
    assert replacement.id != original.id


@pytest.mark.asyncio
async def test_adopt_legacy_connections_binds_only_current_workspace(
    session, test_user, test_workspace
):
    legacy = BankConnection(
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        provider="pluggy",
        external_id="item-legacy",
        institution_name="Bank",
        credentials={"item_id": "item-legacy"},
    )
    session.add(legacy)
    with patch("app.providers.pluggy.PluggyProvider.verify_credentials", new_callable=AsyncMock):
        active = await service.save_pluggy_credential(
            session, test_workspace.id, test_user.id, "client-new", "secret-new"
        )
    await session.commit()

    provider = AsyncMock()
    provider.get_accounts = AsyncMock(return_value=[])
    with patch("app.services.provider_credential_service.resolve_provider", return_value=(provider, active)):
        adopted = await service.adopt_legacy_pluggy_connections(session, test_workspace.id)
    await session.commit()
    await session.refresh(legacy)
    assert adopted == 1
    assert legacy.provider_credential_id == active.id


@pytest.mark.asyncio
async def test_legacy_connection_never_switches_to_new_active_profile_implicitly(
    session, test_user, test_workspace
):
    with patch("app.providers.pluggy.PluggyProvider.verify_credentials", new_callable=AsyncMock):
        await service.save_pluggy_credential(
            session, test_workspace.id, test_user.id, "client-new", "secret-new"
        )
    await session.commit()

    # This is the sync/reconnect path for a pre-feature connection whose
    # credential pointer is null. Without an environment fallback it must fail,
    # never silently use the newly active workspace profile.
    with patch("app.services.provider_credential_service._environment_pluggy_configured", return_value=False):
        with pytest.raises(ProviderNotConfiguredError):
            await service.resolve_provider(
                session,
                test_workspace.id,
                "pluggy",
                prefer_environment_for_legacy=True,
            )


@pytest.mark.asyncio
async def test_unavailable_pinned_credential_never_falls_back_to_environment_provider(
    session, test_workspace
):
    unavailable = service.WorkspaceCredentialUnavailableError(
        "The selected Pluggy credential is unavailable for this workspace."
    )
    with (
        patch(
            "app.services.provider_credential_service.resolve_provider",
            new_callable=AsyncMock,
            side_effect=unavailable,
        ),
        patch("app.services.connection_service.get_provider") as environment_provider,
    ):
        with pytest.raises(service.WorkspaceCredentialUnavailableError):
            await _resolve_provider_for_workspace(
                session,
                test_workspace.id,
                "pluggy",
                uuid.uuid4(),
            )

    environment_provider.assert_not_called()
