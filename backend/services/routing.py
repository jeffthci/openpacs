"""
services/routing.py
────────────────────────────────────────────────────────────
Rules-based auto-routing engine.

A RoutingRule has:
  - Conditions (modality, AE title, study description pattern, etc.)
  - Action: forward to one or more RoutingDestinations via C-STORE SCU

Rules are evaluated in priority order (lower number = higher priority).
First matching rule wins (or all-match mode if configured).

Example rules stored in DB
───────────────────────────
  Priority 1: IF modality = "CT"     → send to CT_WORKSTATION (104)
  Priority 2: IF modality = "MR"     → send to MR_WORKSTATION (104)
  Priority 3: IF ae_title = "MRI_RM" → send to ARCHIVE (11112)
  Priority 99: (default)             → send to PRIMARY_PACS
"""

import logging
from typing import List, Dict, Any

import pynetdicom
from pynetdicom import AE
from pynetdicom.sop_class import (
    CTImageStorage, MRImageStorage, CRImageStorage,
    DigitalXRayImagePresentationStorage,
    UltrasoundImageStorage, NuclearMedicineImageStorage,
    RTStructureSetStorage, PatientRootQueryRetrieveInformationModelMove,
    StudyRootQueryRetrieveInformationModelMove,
)
from sqlalchemy.orm import Session

from models import Study, Series, Instance, RoutingRule, RoutingDestination
from config import settings

log = logging.getLogger(__name__)

# All storage SOPs we can forward
STORAGE_CLASSES = [
    CTImageStorage,
    MRImageStorage,
    CRImageStorage,
    DigitalXRayImagePresentationStorage,
    UltrasoundImageStorage,
    NuclearMedicineImageStorage,
    RTStructureSetStorage,
    "1.2.840.10008.5.1.4.1.1.2.1",  # Enhanced CT
    "1.2.840.10008.5.1.4.1.1.4.1",  # Enhanced MR
    "1.2.840.10008.5.1.4.1.1.12.1", # XA
    "1.2.840.10008.5.1.4.1.1.481.5",# RT Plan
]


def evaluate_and_route(db: Session, study: Study) -> List[Dict[str, Any]]:
    """
    Evaluate all active routing rules against a study.
    Forward matching instances to their configured destinations.
    Returns a list of routing result dicts.
    """
    rules = (
        db.query(RoutingRule)
        .filter(RoutingRule.is_active == True)  # noqa: E712
        .order_by(RoutingRule.priority)
        .all()
    )

    if not rules:
        log.debug(f"[routing] No active rules — skipping study {study.study_instance_uid}")
        return []

    results = []
    matched_destinations = set()

    for rule in rules:
        if _rule_matches(rule, study):
            for dest in rule.destinations:
                if dest.id not in matched_destinations:
                    result = _forward_study(study, dest)
                    results.append(result)
                    matched_destinations.add(dest.id)
            if rule.stop_on_match:
                break  # First-match mode

    return results


def _rule_matches(rule: RoutingRule, study: Study) -> bool:
    """Return True if all conditions in this rule match the study."""
    conditions = rule.conditions or {}

    # Modality check
    if "modality" in conditions:
        rule_mod = conditions["modality"].upper()
        study_mods = [m.upper() for m in (study.modalities_in_study or [])]
        if rule_mod not in study_mods:
            return False

    # AE Title check (calling AE that sent the study)
    if "calling_ae" in conditions:
        if (study.calling_ae_title or "").upper() != conditions["calling_ae"].upper():
            return False

    # Study description pattern
    if "study_description_contains" in conditions:
        pattern = conditions["study_description_contains"].lower()
        if pattern not in (study.study_description or "").lower():
            return False

    # Accession number prefix
    if "accession_prefix" in conditions:
        prefix = conditions["accession_prefix"]
        if not (study.accession_number or "").startswith(prefix):
            return False

    # Body part (from series)
    if "body_part" in conditions:
        body_parts = [s.body_part_examined for s in study.series if s.body_part_examined]
        if conditions["body_part"].upper() not in [bp.upper() for bp in body_parts]:
            return False

    return True


def _forward_study(study: Study, dest: RoutingDestination) -> Dict[str, Any]:
    """
    C-STORE SCU: send all instances in a study to a remote AE.
    """
    import pydicom
    from pathlib import Path

    ae = AE(ae_title=settings.AE_TITLE)
    for sop_class in STORAGE_CLASSES:
        ae.add_requested_context(sop_class)

    log.info(
        f"[routing] Forwarding study {study.study_instance_uid} "
        f"→ {dest.ae_title}@{dest.host}:{dest.port}"
    )

    sent  = 0
    failed = 0

    try:
        assoc = ae.associate(dest.host, dest.port, ae_title=dest.ae_title)
        if not assoc.is_established:
            log.error(f"[routing] Cannot connect to {dest.ae_title}@{dest.host}:{dest.port}")
            return {"destination": dest.ae_title, "status": "connect_failed", "sent": 0}

        for series in study.series:
            for instance in series.instances:
                path = Path(instance.file_path)
                if not path.exists():
                    failed += 1
                    continue
                try:
                    ds = pydicom.dcmread(str(path))
                    status = assoc.send_c_store(ds)
                    if status and status.Status == 0x0000:
                        sent += 1
                    else:
                        failed += 1
                        log.warning(f"[routing] C-STORE failed for {instance.sop_instance_uid}: {status}")
                except Exception as e:
                    failed += 1
                    log.error(f"[routing] Error sending {instance.sop_instance_uid}: {e}")

        assoc.release()

    except Exception as exc:
        log.error(f"[routing] Association error: {exc}", exc_info=True)
        return {"destination": dest.ae_title, "status": "error", "sent": sent, "failed": failed}

    log.info(f"[routing] Forwarded {sent} instances, {failed} failed → {dest.ae_title}")
    return {
        "destination": dest.ae_title,
        "host": dest.host,
        "port": dest.port,
        "status": "ok",
        "sent": sent,
        "failed": failed,
    }
