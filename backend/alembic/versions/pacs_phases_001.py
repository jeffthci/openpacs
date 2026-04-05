"""add_all_pacs_phases

Revision ID: pacs_phases_001
Revises: (your previous revision ID)
Create Date: 2026-04-02

Single migration adding everything from Phase 1-6:
  - partition table
  - storage_filesystem table
  - routing_rule + routing_destination tables
  - audit_log table
  - New columns on user, study, instance
"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    # ── Partition ─────────────────────────────────────────────────
    op.create_table("partition",
        sa.Column("id",               sa.Integer(),     primary_key=True),
        sa.Column("ae_title",         sa.String(16),    unique=True, nullable=False),
        sa.Column("description",      sa.String(255),   default=""),
        sa.Column("is_active",        sa.Boolean(),     default=True),
        sa.Column("storage_prefix",   sa.String(128),   default=""),
        sa.Column("storage_quota_gb", sa.Integer(),     nullable=True),
        sa.Column("dicom_port",       sa.Integer(),     nullable=True),
        sa.Column("accept_any_ae",    sa.Boolean(),     default=False),
        sa.Column("isolated_qido",    sa.Boolean(),     default=True),
        sa.Column("retention_days",   sa.Integer(),     nullable=True),
        sa.Column("created_at",       sa.DateTime(),    server_default=sa.func.now()),
        sa.Column("updated_at",       sa.DateTime(),    server_default=sa.func.now()),
    )
    op.create_index("ix_partition_ae_title", "partition", ["ae_title"])

    # ── Storage filesystem ────────────────────────────────────────
    op.create_table("storage_filesystem",
        sa.Column("id",              sa.Integer(),    primary_key=True),
        sa.Column("path",            sa.String(512),  unique=True, nullable=False),
        sa.Column("label",           sa.String(128),  default=""),
        sa.Column("tier",            sa.String(32),   default="primary"),
        sa.Column("is_active",       sa.Boolean(),    default=True),
        sa.Column("is_writable",     sa.Boolean(),    default=True),
        sa.Column("total_bytes",     sa.BigInteger(), default=0),
        sa.Column("used_bytes",      sa.BigInteger(), default=0),
        sa.Column("available_bytes", sa.BigInteger(), default=0),
        sa.Column("percent_used",    sa.Float(),      default=0.0),
        sa.Column("max_gb",          sa.Integer(),    nullable=True),
        sa.Column("created_at",      sa.DateTime(),   server_default=sa.func.now()),
        sa.Column("updated_at",      sa.DateTime(),   server_default=sa.func.now()),
    )

    # ── Routing rule ──────────────────────────────────────────────
    op.create_table("routing_rule",
        sa.Column("id",            sa.Integer(),   primary_key=True),
        sa.Column("name",          sa.String(128), nullable=False),
        sa.Column("description",   sa.Text(),      default=""),
        sa.Column("priority",      sa.Integer(),   default=100),
        sa.Column("is_active",     sa.Boolean(),   default=True),
        sa.Column("stop_on_match", sa.Boolean(),   default=True),
        sa.Column("conditions",    sa.JSON(),      default={}),
        sa.Column("partition_id",  sa.Integer(),   sa.ForeignKey("partition.id"), nullable=True),
        sa.Column("created_at",    sa.DateTime(),  server_default=sa.func.now()),
        sa.Column("updated_at",    sa.DateTime(),  server_default=sa.func.now()),
    )

    op.create_table("routing_destination",
        sa.Column("id",          sa.Integer(),   primary_key=True),
        sa.Column("rule_id",     sa.Integer(),   sa.ForeignKey("routing_rule.id"), nullable=False),
        sa.Column("ae_title",    sa.String(16),  nullable=False),
        sa.Column("host",        sa.String(255), nullable=False),
        sa.Column("port",        sa.Integer(),   default=104),
        sa.Column("is_active",   sa.Boolean(),   default=True),
        sa.Column("description", sa.String(255), default=""),
    )

    # ── Audit log ─────────────────────────────────────────────────
    op.create_table("audit_log",
        sa.Column("id",            sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type",    sa.String(64),   nullable=False),
        sa.Column("event_time",    sa.DateTime(),   server_default=sa.func.now()),
        sa.Column("user_id",       sa.Integer(),    sa.ForeignKey("user.id"), nullable=True),
        sa.Column("username",      sa.String(64),   nullable=True),
        sa.Column("ip_address",    sa.String(45),   nullable=True),
        sa.Column("user_agent",    sa.String(255),  nullable=True),
        sa.Column("resource_type", sa.String(32),   nullable=True),
        sa.Column("resource_id",   sa.String(128),  nullable=True),
        sa.Column("action",        sa.String(32),   nullable=True),
        sa.Column("outcome",       sa.String(16),   default="success"),
        sa.Column("description",   sa.Text(),       nullable=True),
        sa.Column("metadata_json", sa.JSON(),       nullable=True),
        sa.Column("entry_hash",    sa.String(64),   nullable=True),
    )
    op.create_index("ix_audit_log_event_type",  "audit_log", ["event_type"])
    op.create_index("ix_audit_log_event_time",  "audit_log", ["event_time"])
    op.create_index("ix_audit_log_user_id",     "audit_log", ["user_id"])

    # ── Add columns to existing tables ───────────────────────────

    # user
    op.add_column("user", sa.Column("role",       sa.String(32),  server_default="viewer"))
    op.add_column("user", sa.Column("last_login",  sa.DateTime(),  nullable=True))

    # study
    op.add_column("study", sa.Column("partition_id",      sa.Integer(), sa.ForeignKey("partition.id"), nullable=True))
    op.add_column("study", sa.Column("calling_ae_title",  sa.String(16),  nullable=True))
    op.add_column("study", sa.Column("retain_until",      sa.DateTime(),  nullable=True))
    op.add_column("study", sa.Column("created_at",        sa.DateTime(),  server_default=sa.func.now()))
    op.create_index("ix_study_partition_id", "study", ["partition_id"])

    # instance
    op.add_column("instance", sa.Column("transfer_syntax", sa.String(64), nullable=True))
    op.add_column("instance", sa.Column("acquired_at",     sa.DateTime(), nullable=True))


def downgrade():
    # instance
    op.drop_column("instance", "acquired_at")
    op.drop_column("instance", "transfer_syntax")

    # study
    op.drop_index("ix_study_partition_id", "study")
    op.drop_column("study", "created_at")
    op.drop_column("study", "retain_until")
    op.drop_column("study", "calling_ae_title")
    op.drop_column("study", "partition_id")

    # user
    op.drop_column("user", "last_login")
    op.drop_column("user", "role")

    # tables
    op.drop_index("ix_audit_log_user_id",    "audit_log")
    op.drop_index("ix_audit_log_event_time", "audit_log")
    op.drop_index("ix_audit_log_event_type", "audit_log")
    op.drop_table("audit_log")
    op.drop_table("routing_destination")
    op.drop_table("routing_rule")
    op.drop_table("storage_filesystem")
    op.drop_index("ix_partition_ae_title", "partition")
    op.drop_table("partition")
