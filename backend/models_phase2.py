"""
models_phase2.py
────────────────────────────────────────────────────────────
New DB models for Phase 2 features.
Merge these into your existing models.py.

New models
──────────
  WorklistItem      – scheduled procedures (MWL)
  CompressionJob    – track compression requests
  AnonymizationJob  – track de-identification jobs
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean, Column, DateTime, Integer,
    String, Text, BigInteger,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ══════════════════════════════════════════════════════════════════
#  Modality Worklist
# ══════════════════════════════════════════════════════════════════

class WorklistItem(Base):
    """
    Scheduled procedure entry returned to modalities via MWL C-FIND.
    Created by RIS/HIS or manually via the REST API.
    """
    __tablename__ = "worklist_item"

    id                         = Column(Integer, primary_key=True, index=True)
    patient_name               = Column(String(256), nullable=False, index=True)
    patient_id                 = Column(String(64),  nullable=False, index=True)
    date_of_birth              = Column(String(8))
    sex                        = Column(String(2))

    # Procedure
    accession_number           = Column(String(64), index=True)
    study_instance_uid         = Column(String(128), unique=True, index=True)
    study_description          = Column(String(256))
    requested_procedure_id     = Column(String(64))
    procedure_description      = Column(String(256))
    modality                   = Column(String(16), index=True)
    priority                   = Column(String(16), default="ROUTINE")

    # Scheduling
    scheduled_date             = Column(String(8), index=True)   # YYYYMMDD
    scheduled_time             = Column(String(6))               # HHMMSS
    station_ae_title           = Column(String(16))
    station_name               = Column(String(64))
    performing_physician       = Column(String(128))
    referring_physician        = Column(String(128))

    # State
    is_completed               = Column(Boolean, default=False, index=True)
    completed_at               = Column(DateTime, nullable=True)
    notes                      = Column(Text, default="")

    created_at                 = Column(DateTime, default=datetime.utcnow)
    updated_at                 = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ══════════════════════════════════════════════════════════════════
#  Background job base columns
# ══════════════════════════════════════════════════════════════════

class CompressionJob(Base):
    __tablename__ = "compression_job"

    id             = Column(Integer, primary_key=True, index=True)
    study_uid      = Column(String(128), index=True)
    target_syntax  = Column(String(64))
    syntax_name    = Column(String(64))
    status         = Column(String(32), default="queued", index=True)  # queued|running|completed|error
    total          = Column(Integer, default=0)
    done           = Column(Integer, default=0)
    failed         = Column(Integer, default=0)
    error_detail   = Column(Text, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    completed_at   = Column(DateTime, nullable=True)


class AnonymizationJob(Base):
    __tablename__ = "anonymization_job"

    id           = Column(Integer, primary_key=True, index=True)
    study_uid    = Column(String(128), index=True)
    mode         = Column(String(32), default="full")
    pseudonym    = Column(String(128), nullable=True)
    keep_uids    = Column(Boolean, default=False)
    import_back  = Column(Boolean, default=False)
    status       = Column(String(32), default="queued", index=True)
    total        = Column(Integer, default=0)
    done         = Column(Integer, default=0)
    failed       = Column(Integer, default=0)
    job_token    = Column(String(64), unique=True, index=True)
    new_study_uid = Column(String(128), nullable=True)
    error_detail = Column(Text, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


# ══════════════════════════════════════════════════════════════════
#  Alembic migration script
# ══════════════════════════════════════════════════════════════════

MIGRATION_PHASE2 = '''
"""add_phase2_tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        "worklist_item",
        sa.Column("id",                         sa.Integer(),  primary_key=True),
        sa.Column("patient_name",               sa.String(256), nullable=False),
        sa.Column("patient_id",                 sa.String(64),  nullable=False),
        sa.Column("date_of_birth",              sa.String(8),   nullable=True),
        sa.Column("sex",                        sa.String(2),   nullable=True),
        sa.Column("accession_number",           sa.String(64),  nullable=True),
        sa.Column("study_instance_uid",         sa.String(128), unique=True),
        sa.Column("study_description",          sa.String(256), nullable=True),
        sa.Column("requested_procedure_id",     sa.String(64),  nullable=True),
        sa.Column("procedure_description",      sa.String(256), nullable=True),
        sa.Column("modality",                   sa.String(16),  nullable=True),
        sa.Column("priority",                   sa.String(16),  default="ROUTINE"),
        sa.Column("scheduled_date",             sa.String(8),   nullable=True),
        sa.Column("scheduled_time",             sa.String(6),   nullable=True),
        sa.Column("station_ae_title",           sa.String(16),  nullable=True),
        sa.Column("station_name",               sa.String(64),  nullable=True),
        sa.Column("performing_physician",       sa.String(128), nullable=True),
        sa.Column("referring_physician",        sa.String(128), nullable=True),
        sa.Column("is_completed",               sa.Boolean(),   default=False),
        sa.Column("completed_at",               sa.DateTime(),  nullable=True),
        sa.Column("notes",                      sa.Text(),      default=""),
        sa.Column("created_at",                 sa.DateTime(),  server_default=sa.func.now()),
        sa.Column("updated_at",                 sa.DateTime(),  server_default=sa.func.now()),
    )
    op.create_table(
        "compression_job",
        sa.Column("id",           sa.Integer(), primary_key=True),
        sa.Column("study_uid",    sa.String(128)),
        sa.Column("target_syntax",sa.String(64)),
        sa.Column("syntax_name",  sa.String(64)),
        sa.Column("status",       sa.String(32), default="queued"),
        sa.Column("total",        sa.Integer(), default=0),
        sa.Column("done",         sa.Integer(), default=0),
        sa.Column("failed",       sa.Integer(), default=0),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at",   sa.DateTime(), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "anonymization_job",
        sa.Column("id",            sa.Integer(), primary_key=True),
        sa.Column("study_uid",     sa.String(128)),
        sa.Column("mode",          sa.String(32), default="full"),
        sa.Column("pseudonym",     sa.String(128), nullable=True),
        sa.Column("keep_uids",     sa.Boolean(), default=False),
        sa.Column("import_back",   sa.Boolean(), default=False),
        sa.Column("status",        sa.String(32), default="queued"),
        sa.Column("total",         sa.Integer(), default=0),
        sa.Column("done",          sa.Integer(), default=0),
        sa.Column("failed",        sa.Integer(), default=0),
        sa.Column("job_token",     sa.String(64), unique=True),
        sa.Column("new_study_uid", sa.String(128), nullable=True),
        sa.Column("error_detail",  sa.Text(), nullable=True),
        sa.Column("created_at",    sa.DateTime(), server_default=sa.func.now()),
        sa.Column("completed_at",  sa.DateTime(), nullable=True),
    )

def downgrade():
    op.drop_table("worklist_item")
    op.drop_table("compression_job")
    op.drop_table("anonymization_job")
'''
