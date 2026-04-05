"""
models_additions.py
────────────────────────────────────────────────────────────
Database model ADDITIONS to the existing models.py.

Add these classes/columns to your existing models.py file,
or run the Alembic migration generated below.

New models
──────────
  StorageFilesystem   – configurable storage roots with usage stats
  RoutingRule         – auto-routing rules (modality, AE, description)
  RoutingDestination  – target AE title + host + port for routing

New columns on existing models
───────────────────────────────
  Study.calling_ae_title    – AE that sent the study (for routing rules)
  Study.retain_until        – optional absolute retention date
  Study.created_at          – timestamp of first receipt
  Instance.acquired_at      – datetime from DICOM tags
  Instance.transfer_syntax  – original transfer syntax UID
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, JSON, String, Text, BigInteger,
)
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  Storage filesystem registry
# ══════════════════════════════════════════════════════════════════════════════

class StorageFilesystem(Base):
    """
    One row per configured storage root.
    Allows multiple drives / mount points with different tiers.

    Example rows:
      path=/mnt/nvme0  label="Primary SSD"   tier=primary   max_gb=2000
      path=/mnt/hdd0   label="Archive HDD"   tier=archive   max_gb=20000
    """
    __tablename__ = "storage_filesystem"

    id              = Column(Integer, primary_key=True, index=True)
    path            = Column(String(512), unique=True, nullable=False)
    label           = Column(String(128), default="")
    tier            = Column(String(32), default="primary")   # primary | archive
    is_active       = Column(Boolean, default=True)
    is_writable     = Column(Boolean, default=True)

    # Capacity (updated by sync_storage_stats task)
    total_bytes     = Column(BigInteger, default=0)
    used_bytes      = Column(BigInteger, default=0)
    available_bytes = Column(BigInteger, default=0)
    percent_used    = Column(Float, default=0.0)

    # Optional quota
    max_gb          = Column(Integer, nullable=True)

    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<StorageFilesystem {self.label} ({self.tier}) {self.percent_used}% full>"


# ══════════════════════════════════════════════════════════════════════════════
#  Routing rules + destinations
# ══════════════════════════════════════════════════════════════════════════════

class RoutingRule(Base):
    """
    One routing rule. Rules are evaluated in priority order (lowest first).

    conditions: JSON dict, e.g.:
      {"modality": "CT"}
      {"modality": "MR", "calling_ae": "MRI_ROOM1"}
      {"study_description_contains": "CHEST"}
      {}   ← matches everything (catch-all / default route)

    stop_on_match: if True, no further rules are checked after this one fires.
    """
    __tablename__ = "routing_rule"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(128), nullable=False)
    description   = Column(Text, default="")
    priority      = Column(Integer, default=100)
    is_active     = Column(Boolean, default=True)
    stop_on_match = Column(Boolean, default=True)

    conditions    = Column(JSON, default=dict)  # see docstring above

    destinations  = relationship("RoutingDestination", back_populates="rule",
                                  cascade="all, delete-orphan")

    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<RoutingRule [{self.priority}] {self.name}>"


class RoutingDestination(Base):
    """
    A C-STORE SCU target associated with a routing rule.
    One rule can have multiple destinations (fan-out).
    """
    __tablename__ = "routing_destination"

    id         = Column(Integer, primary_key=True, index=True)
    rule_id    = Column(Integer, ForeignKey("routing_rule.id"), nullable=False)
    ae_title   = Column(String(16), nullable=False)
    host       = Column(String(255), nullable=False)
    port       = Column(Integer, default=104)
    is_active  = Column(Boolean, default=True)
    description = Column(String(255), default="")

    rule = relationship("RoutingRule", back_populates="destinations")

    def __repr__(self):
        return f"<RoutingDestination {self.ae_title}@{self.host}:{self.port}>"


# ══════════════════════════════════════════════════════════════════════════════
#  Alembic migration script (add_pacs_phase1_gaps)
# ══════════════════════════════════════════════════════════════════════════════
MIGRATION_SCRIPT = '''
"""add_pacs_phase1_gaps

Revision ID: a1b2c3d4e5f6
Revises: <your_previous_revision>
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # ── storage_filesystem table ──────────────────────────────────────────
    op.create_table(
        "storage_filesystem",
        sa.Column("id",              sa.Integer(),     primary_key=True),
        sa.Column("path",            sa.String(512),   unique=True, nullable=False),
        sa.Column("label",           sa.String(128),   default=""),
        sa.Column("tier",            sa.String(32),    default="primary"),
        sa.Column("is_active",       sa.Boolean(),     default=True),
        sa.Column("is_writable",     sa.Boolean(),     default=True),
        sa.Column("total_bytes",     sa.BigInteger(),  default=0),
        sa.Column("used_bytes",      sa.BigInteger(),  default=0),
        sa.Column("available_bytes", sa.BigInteger(),  default=0),
        sa.Column("percent_used",    sa.Float(),       default=0.0),
        sa.Column("max_gb",          sa.Integer(),     nullable=True),
        sa.Column("created_at",      sa.DateTime(),    default=sa.func.now()),
        sa.Column("updated_at",      sa.DateTime(),    default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ── routing_rule table ────────────────────────────────────────────────
    op.create_table(
        "routing_rule",
        sa.Column("id",            sa.Integer(),  primary_key=True),
        sa.Column("name",          sa.String(128), nullable=False),
        sa.Column("description",   sa.Text(),      default=""),
        sa.Column("priority",      sa.Integer(),   default=100),
        sa.Column("is_active",     sa.Boolean(),   default=True),
        sa.Column("stop_on_match", sa.Boolean(),   default=True),
        sa.Column("conditions",    sa.JSON(),      default={}),
        sa.Column("created_at",    sa.DateTime(),  default=sa.func.now()),
        sa.Column("updated_at",    sa.DateTime(),  default=sa.func.now()),
    )

    # ── routing_destination table ─────────────────────────────────────────
    op.create_table(
        "routing_destination",
        sa.Column("id",          sa.Integer(),  primary_key=True),
        sa.Column("rule_id",     sa.Integer(),  sa.ForeignKey("routing_rule.id"), nullable=False),
        sa.Column("ae_title",    sa.String(16), nullable=False),
        sa.Column("host",        sa.String(255), nullable=False),
        sa.Column("port",        sa.Integer(),  default=104),
        sa.Column("is_active",   sa.Boolean(),  default=True),
        sa.Column("description", sa.String(255), default=""),
    )

    # ── New columns on study ──────────────────────────────────────────────
    op.add_column("study", sa.Column("calling_ae_title", sa.String(16), nullable=True))
    op.add_column("study", sa.Column("retain_until",     sa.DateTime(), nullable=True))
    op.add_column("study", sa.Column("created_at",       sa.DateTime(), server_default=sa.func.now()))

    # ── New columns on instance ───────────────────────────────────────────
    op.add_column("instance", sa.Column("acquired_at",     sa.DateTime(),  nullable=True))
    op.add_column("instance", sa.Column("transfer_syntax", sa.String(64),  nullable=True))

def downgrade():
    op.drop_table("routing_destination")
    op.drop_table("routing_rule")
    op.drop_table("storage_filesystem")
    op.drop_column("study",    "calling_ae_title")
    op.drop_column("study",    "retain_until")
    op.drop_column("study",    "created_at")
    op.drop_column("instance", "acquired_at")
    op.drop_column("instance", "transfer_syntax")
'''
