"""
models.py  — complete consolidated model file
────────────────────────────────────────────────────────────
Replace your existing models.py with this file.
Includes all original models plus Phase 1-6 additions:
  - Partition (Phase 5)
  - StorageFilesystem (Phase 1)
  - RoutingRule + RoutingDestination (Phase 1/4)
  - AuditLog (Phase 6)
  - User.role column
  - Study.partition_id + calling_ae_title + retain_until + created_at
  - Instance.acquired_at + transfer_syntax
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float,
    ForeignKey, Integer, JSON, String, Text, BigInteger,
)
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  Auth
# ══════════════════════════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "user"

    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String(64),  unique=True, nullable=False, index=True)
    email           = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role            = Column(String(32),  default="viewer")   # viewer|radiologist|technician|admin
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    last_login      = Column(DateTime, nullable=True)

    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")


# ══════════════════════════════════════════════════════════════════════════════
#  Partition  (Phase 5 — virtual AE partitions)
# ══════════════════════════════════════════════════════════════════════════════

class Partition(Base):
    __tablename__ = "partition"

    id               = Column(Integer, primary_key=True, index=True)
    ae_title         = Column(String(16),  unique=True, nullable=False, index=True)
    description      = Column(String(255), default="")
    is_active        = Column(Boolean, default=True)

    storage_prefix   = Column(String(128), default="")
    storage_quota_gb = Column(Integer, nullable=True)

    dicom_port       = Column(Integer, nullable=True)
    accept_any_ae    = Column(Boolean, default=False)
    isolated_qido    = Column(Boolean, default=True)

    retention_days   = Column(Integer, nullable=True)

    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    studies = relationship("Study", back_populates="partition")

    def __repr__(self):
        return f"<Partition {self.ae_title}>"


# ══════════════════════════════════════════════════════════════════════════════
#  DICOM hierarchy
# ══════════════════════════════════════════════════════════════════════════════

class Patient(Base):
    __tablename__ = "patient"

    id            = Column(Integer, primary_key=True, index=True)
    patient_id    = Column(String(64),  unique=True, nullable=False, index=True)
    patient_name  = Column(String(255), nullable=True, index=True)
    date_of_birth = Column(String(8),   nullable=True)
    sex           = Column(String(1),   nullable=True)
    other_ids     = Column(JSON,        default=list)

    studies = relationship("Study", back_populates="patient", cascade="all, delete-orphan")


class Study(Base):
    __tablename__ = "study"

    id                                 = Column(Integer, primary_key=True, index=True)
    patient_id                         = Column(Integer, ForeignKey("patient.id"), nullable=False, index=True)
    partition_id                       = Column(Integer, ForeignKey("partition.id"), nullable=True, index=True)

    study_instance_uid                 = Column(String(64), unique=True, nullable=False, index=True)
    study_date                         = Column(String(8),  nullable=True, index=True)
    study_time                         = Column(String(14), nullable=True)
    study_description                  = Column(String(255), nullable=True)
    study_id                           = Column(String(16),  nullable=True)
    accession_number                   = Column(String(64),  nullable=True, index=True)
    referring_physician                = Column(String(255), nullable=True)
    modalities_in_study                = Column(JSON, default=list)

    number_of_study_related_series     = Column(Integer, default=0)
    number_of_study_related_instances  = Column(Integer, default=0)

    # Phase 1 additions
    calling_ae_title                   = Column(String(16), nullable=True)
    retain_until                       = Column(DateTime,   nullable=True)
    created_at                         = Column(DateTime,   default=datetime.utcnow)

    patient   = relationship("Patient",   back_populates="studies")
    partition = relationship("Partition",  back_populates="studies")
    series    = relationship("Series",    back_populates="study",   cascade="all, delete-orphan")
    reports   = relationship("Report",    back_populates="study",   cascade="all, delete-orphan")


class Series(Base):
    __tablename__ = "series"

    id                               = Column(Integer, primary_key=True, index=True)
    study_id                         = Column(Integer, ForeignKey("study.id"), nullable=False, index=True)

    series_instance_uid              = Column(String(64), unique=True, nullable=False, index=True)
    series_number                    = Column(Integer, nullable=True)
    series_description               = Column(String(255), nullable=True)
    modality                         = Column(String(16),  nullable=True, index=True)
    body_part_examined               = Column(String(64),  nullable=True)
    performed_procedure              = Column(String(255), nullable=True)
    number_of_series_related_instances = Column(Integer, default=0)

    study     = relationship("Study",    back_populates="series")
    instances = relationship("Instance", back_populates="series", cascade="all, delete-orphan",
                              order_by="Instance.instance_number")


class Instance(Base):
    __tablename__ = "instance"

    id                = Column(Integer, primary_key=True, index=True)
    series_id         = Column(Integer, ForeignKey("series.id"), nullable=False, index=True)

    sop_instance_uid  = Column(String(64), unique=True, nullable=False, index=True)
    sop_class_uid     = Column(String(64), nullable=True)
    instance_number   = Column(Integer,    nullable=True)

    file_path         = Column(String(512), nullable=False)
    file_size         = Column(BigInteger,  nullable=True)

    # Phase 1 additions
    transfer_syntax   = Column(String(64),  nullable=True)
    acquired_at       = Column(DateTime,    nullable=True)

    # Image properties
    rows              = Column(Integer, nullable=True)
    columns           = Column(Integer, nullable=True)
    number_of_frames  = Column(Integer, default=1)
    bits_allocated    = Column(Integer, nullable=True)
    photometric       = Column(String(32), nullable=True)
    window_center     = Column(String(32), nullable=True)
    window_width      = Column(String(32), nullable=True)

    series = relationship("Series", back_populates="instances")


# ══════════════════════════════════════════════════════════════════════════════
#  Reports
# ══════════════════════════════════════════════════════════════════════════════

class Report(Base):
    __tablename__ = "report"

    id           = Column(Integer, primary_key=True, index=True)
    study_id     = Column(Integer, ForeignKey("study.id"), nullable=False, index=True)
    author_id    = Column(Integer, ForeignKey("user.id"),  nullable=True)

    status       = Column(String(32), default="draft")   # draft | signed | addendum
    report_text  = Column(Text,       nullable=True)
    impression   = Column(Text,       nullable=True)
    pdf_path     = Column(String(512), nullable=True)

    created_at   = Column(DateTime, default=datetime.utcnow)
    signed_at    = Column(DateTime, nullable=True)

    study  = relationship("Study", back_populates="reports")
    author = relationship("User")


# ══════════════════════════════════════════════════════════════════════════════
#  Storage filesystem registry  (Phase 1)
# ══════════════════════════════════════════════════════════════════════════════

class StorageFilesystem(Base):
    __tablename__ = "storage_filesystem"

    id              = Column(Integer,    primary_key=True, index=True)
    path            = Column(String(512), unique=True, nullable=False)
    label           = Column(String(128), default="")
    tier            = Column(String(32),  default="primary")
    is_active       = Column(Boolean, default=True)
    is_writable     = Column(Boolean, default=True)

    total_bytes     = Column(BigInteger, default=0)
    used_bytes      = Column(BigInteger, default=0)
    available_bytes = Column(BigInteger, default=0)
    percent_used    = Column(Float,      default=0.0)
    max_gb          = Column(Integer,    nullable=True)

    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ══════════════════════════════════════════════════════════════════════════════
#  Routing  (Phase 1/4)
# ══════════════════════════════════════════════════════════════════════════════

class RoutingRule(Base):
    __tablename__ = "routing_rule"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(128), nullable=False)
    description   = Column(Text,        default="")
    priority      = Column(Integer,     default=100)
    is_active     = Column(Boolean,     default=True)
    stop_on_match = Column(Boolean,     default=True)
    conditions    = Column(JSON,        default=dict)

    partition_id  = Column(Integer, ForeignKey("partition.id"), nullable=True)

    destinations  = relationship("RoutingDestination", back_populates="rule",
                                  cascade="all, delete-orphan")
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RoutingDestination(Base):
    __tablename__ = "routing_destination"

    id          = Column(Integer, primary_key=True, index=True)
    rule_id     = Column(Integer, ForeignKey("routing_rule.id"), nullable=False)
    ae_title    = Column(String(16),  nullable=False)
    host        = Column(String(255), nullable=False)
    port        = Column(Integer,     default=104)
    is_active   = Column(Boolean,     default=True)
    description = Column(String(255), default="")

    rule = relationship("RoutingRule", back_populates="destinations")


# ══════════════════════════════════════════════════════════════════════════════
#  Audit log  (Phase 6)
# ══════════════════════════════════════════════════════════════════════════════

class AuditLog(Base):
    __tablename__ = "audit_log"

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    event_type     = Column(String(64),  nullable=False, index=True)
    event_time     = Column(DateTime,    nullable=False, default=datetime.utcnow, index=True)

    user_id        = Column(Integer, ForeignKey("user.id"), nullable=True)
    username       = Column(String(64),  nullable=True)
    ip_address     = Column(String(45),  nullable=True)
    user_agent     = Column(String(255), nullable=True)

    resource_type  = Column(String(32),  nullable=True)
    resource_id    = Column(String(128), nullable=True)
    action         = Column(String(32),  nullable=True)
    outcome        = Column(String(16),  nullable=False, default="success")

    description    = Column(Text, nullable=True)
    metadata_json  = Column(JSON, nullable=True)

    entry_hash     = Column(String(64), nullable=True)

    user = relationship("User", back_populates="audit_logs")


# ══════════════════════════════════════════════════════════════════════════════
#  Modality Worklist  (MWL)
# ══════════════════════════════════════════════════════════════════════════════

class WorklistItem(Base):
    __tablename__ = "worklist_item"

    id                     = Column(Integer, primary_key=True, index=True)
    patient_name           = Column(String(255), nullable=False)
    patient_id             = Column(String(64),  nullable=False, index=True)
    patient_dob            = Column(String(8),   nullable=True)   # YYYYMMDD
    patient_sex            = Column(String(1),   nullable=True)   # M/F/O

    accession_number       = Column(String(64),  unique=True, nullable=False, index=True)
    requested_procedure    = Column(String(255), nullable=False)
    modality               = Column(String(16),  nullable=False)
    scheduled_date         = Column(String(8),   nullable=True)   # YYYYMMDD
    scheduled_time         = Column(String(6),   nullable=True)   # HHMMSS
    scheduled_ae_title     = Column(String(16),  nullable=True)
    referring_physician    = Column(String(255), nullable=True)
    procedure_description  = Column(Text,        nullable=True)
    partition_ae           = Column(String(16),  nullable=True)

    status                 = Column(String(32),  default="scheduled", index=True)
    # scheduled | arrived | completed | cancelled

    study_id               = Column(Integer, ForeignKey("study.id"), nullable=True)
    created_at             = Column(DateTime, default=datetime.utcnow)
    updated_at             = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    study = relationship("Study", foreign_keys=[study_id])

    def __repr__(self):
        return f"<WorklistItem {self.accession_number} {self.status}>"
