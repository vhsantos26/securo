"""Guards for invariants of this fork that a clean upstream merge can break."""
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
UPSTREAM_IMAGE_PREFIX = "ghcr.io/securo-finance/"


def _services(filename: str) -> dict:
    path = REPO / filename
    if not path.exists():
        pytest.skip(f"{filename} is not part of this checkout")
    return yaml.safe_load(path.read_text(encoding="utf-8"))["services"]


def test_vps_override_replaces_every_upstream_image():
    """The VPS must run the code it built, never the published upstream images:
    their Alembic chain differs and would be applied to this fork's database."""
    base = _services("docker-compose.prod.yml")
    override = _services("docker-compose.vps.yml")
    leaked = sorted(
        name
        for name, service in base.items()
        if str(service.get("image", "")).startswith(UPSTREAM_IMAGE_PREFIX)
        and str(override.get(name, {}).get("image", UPSTREAM_IMAGE_PREFIX)).startswith(
            UPSTREAM_IMAGE_PREFIX
        )
    )
    assert not leaked, f"add these services to docker-compose.vps.yml: {leaked}"


def test_credit_card_accounting_mode_keeps_the_fork_names():
    """This fork stores 'purchase_date' / 'invoice_due_date' (migration 090).
    Upstream code comparing against 'cash' / 'accrual' merges cleanly and then
    silently takes the wrong branch."""
    # Files where the words mean something else, or map the legacy values.
    allowed = {"admin_service.py", "text_similarity.py", "document_reader.py"}
    legacy = re.compile(r"""(["'])(?:cash|accrual)\1""")
    offenders = [
        f"{path.relative_to(REPO)}:{number}"
        for folder in ("backend/app", "backend/mcp_server")
        for path in sorted((REPO / folder).rglob("*.py"))
        if path.name not in allowed
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if legacy.search(line)
    ]
    assert not offenders, f"use 'purchase_date' / 'invoice_due_date': {offenders}"
