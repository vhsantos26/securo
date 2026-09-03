"""add workspace-scoped provider credentials

Revision ID: 091
Revises: 090
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "091"
down_revision: Union[str, None] = "090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_provider_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_workspace_provider_credentials_workspace_id", "workspace_provider_credentials", ["workspace_id"])
    op.create_index("ix_workspace_provider_credentials_provider", "workspace_provider_credentials", ["provider"])
    op.create_index(
        "uq_workspace_provider_credentials_active",
        "workspace_provider_credentials",
        ["workspace_id", "provider"],
        unique=True,
        postgresql_where=sa.text("is_active AND retired_at IS NULL"),
    )
    op.add_column(
        "bank_connections",
        sa.Column("provider_credential_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_bank_connections_provider_credential_id", "bank_connections", ["provider_credential_id"])
    op.create_foreign_key(
        "fk_bank_connections_provider_credential_id",
        "bank_connections",
        "workspace_provider_credentials",
        ["provider_credential_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_bank_connections_provider_credential_id", "bank_connections", type_="foreignkey")
    op.drop_index("ix_bank_connections_provider_credential_id", table_name="bank_connections")
    op.drop_column("bank_connections", "provider_credential_id")
    op.drop_index("uq_workspace_provider_credentials_active", table_name="workspace_provider_credentials")
    op.drop_index("ix_workspace_provider_credentials_provider", table_name="workspace_provider_credentials")
    op.drop_index("ix_workspace_provider_credentials_workspace_id", table_name="workspace_provider_credentials")
    op.drop_table("workspace_provider_credentials")
