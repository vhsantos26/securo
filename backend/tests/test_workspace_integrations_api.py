from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_workspace_owner_can_save_pluggy_credentials_without_secret_round_trip(
    client: AsyncClient, auth_headers, test_workspace
):
    with patch("app.providers.pluggy.PluggyProvider.verify_credentials", new_callable=AsyncMock):
        response = await client.put(
            f"/api/workspaces/{test_workspace.id}/integrations/pluggy",
            headers=auth_headers,
            json={"client_id": "client-123456", "client_secret": "super-secret"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["source"] == "workspace"
    assert body["client_id_hint"] == "…3456"
    assert "client_secret" not in body
    assert "super-secret" not in response.text

    listed = await client.get(
        f"/api/workspaces/{test_workspace.id}/integrations", headers=auth_headers
    )
    assert listed.status_code == 200
    assert listed.json()[0]["active_credential_id"] == body["active_credential_id"]
