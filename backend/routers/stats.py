"""
routers/stats.py
────────────────────────────────────────────────────────────
Analytics and reporting endpoints.

  GET /api/stats/overview         overall counts + storage
  GET /api/stats/daily            studies received per day (last N days)
  GET /api/stats/modality         study count breakdown by modality
  GET /api/stats/hourly           studies by hour of day (heatmap data)
  GET /api/stats/top-referring    top referring physicians
  GET /api/stats/storage-trend    storage used over time
"""

from datetime import datetime, timedelta, date
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
from models import Study, Series, Instance, Patient

router = APIRouter(prefix="/stats", tags=["Analytics"])


@router.get("/overview")
def stats_overview(
    db: Session = Depends(get_db),
    _u          = Depends(get_current_user),
):
    """High-level server stats for the dashboard header."""
    today  = date.today().strftime("%Y%m%d")
    week_ago = (date.today() - timedelta(days=7)).strftime("%Y%m%d")

    total_patients  = db.query(func.count(Patient.id)).scalar() or 0
    total_studies   = db.query(func.count(Study.id)).scalar() or 0
    total_instances = db.query(func.count(Instance.id)).scalar() or 0

    studies_today = db.query(func.count(Study.id)).filter(
        Study.study_date == today
    ).scalar() or 0

    studies_this_week = db.query(func.count(Study.id)).filter(
        Study.study_date >= week_ago
    ).scalar() or 0

    total_size_bytes = db.query(func.sum(Instance.file_size)).scalar() or 0

    return {
        "patients":           total_patients,
        "studies":            total_studies,
        "instances":          total_instances,
        "studies_today":      studies_today,
        "studies_this_week":  studies_this_week,
        "storage_gb":         round(total_size_bytes / (1024**3), 2),
    }


@router.get("/daily")
def stats_daily(
    days: int       = Query(30, ge=1, le=365),
    db:   Session   = Depends(get_db),
    _u              = Depends(get_current_user),
):
    """Studies received per calendar day for the last N days."""
    start = (date.today() - timedelta(days=days)).strftime("%Y%m%d")

    rows = (
        db.query(Study.study_date, func.count(Study.id).label("count"))
        .filter(Study.study_date >= start, Study.study_date.isnot(None))
        .group_by(Study.study_date)
        .order_by(Study.study_date)
        .all()
    )

    # Fill gaps with 0
    result = {}
    for i in range(days + 1):
        d = (date.today() - timedelta(days=days - i)).strftime("%Y%m%d")
        result[d] = 0
    for row in rows:
        if row.study_date:
            result[row.study_date] = row.count

    return [{"date": k, "count": v} for k, v in sorted(result.items())]


@router.get("/modality")
def stats_modality(
    days: Optional[int] = Query(None),
    db:   Session       = Depends(get_db),
    _u                  = Depends(get_current_user),
):
    """Study count broken down by modality."""
    q = db.query(Series.modality, func.count(func.distinct(Series.study_id)).label("count"))

    if days:
        start = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
        q = q.join(Study).filter(Study.study_date >= start)

    rows = (
        q.filter(Series.modality.isnot(None))
        .group_by(Series.modality)
        .order_by(func.count(func.distinct(Series.study_id)).desc())
        .all()
    )

    COLORS = {
        "CT":  "#4a9eff", "MR": "#9b59b6", "CR":  "#2ecc71",
        "DX":  "#3498db", "US": "#1abc9c", "NM":  "#e67e22",
        "PT":  "#e74c3c", "MG": "#f39c12", "XA":  "#16a085",
        "RF":  "#8e44ad", "SC": "#95a5a6",
    }

    return [
        {
            "modality": row.modality,
            "count":    row.count,
            "color":    COLORS.get(row.modality, "#7f8c8d"),
        }
        for row in rows
    ]


@router.get("/hourly")
def stats_hourly(
    days: int     = Query(30, ge=1, le=90),
    db:   Session = Depends(get_db),
    _u            = Depends(get_current_user),
):
    """
    Studies by hour of day (0–23) for the last N days.
    Returns 24 buckets — useful for heatmap or bar chart.
    """
    start = datetime.utcnow() - timedelta(days=days)

    # Use study created_at if available, fall back to study_time parsing
    rows = (
        db.query(
            func.extract("hour", Study.created_at).label("hour"),
            func.count(Study.id).label("count"),
        )
        .filter(Study.created_at >= start)
        .group_by(func.extract("hour", Study.created_at))
        .all()
    )

    buckets = {i: 0 for i in range(24)}
    for row in rows:
        if row.hour is not None:
            buckets[int(row.hour)] = row.count

    return [{"hour": h, "count": c} for h, c in buckets.items()]


@router.get("/top-referring")
def stats_top_referring(
    limit: int    = Query(10, ge=1, le=50),
    days:  Optional[int] = Query(None),
    db:    Session       = Depends(get_db),
    _u                   = Depends(get_current_user),
):
    """Top referring physicians by study count."""
    q = (
        db.query(
            Study.referring_physician,
            func.count(Study.id).label("count"),
        )
        .filter(Study.referring_physician.isnot(None), Study.referring_physician != "")
    )
    if days:
        start = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
        q = q.filter(Study.study_date >= start)

    rows = (
        q.group_by(Study.referring_physician)
        .order_by(func.count(Study.id).desc())
        .limit(limit)
        .all()
    )
    return [{"physician": r.referring_physician, "count": r.count} for r in rows]


@router.get("/storage-trend")
def stats_storage_trend(
    days: int     = Query(30, ge=1, le=365),
    db:   Session = Depends(get_db),
    _u            = Depends(get_current_user),
):
    """
    Cumulative storage used (GB) per day for the last N days.
    Approximated from instance file_size and created_at.
    """
    start = (date.today() - timedelta(days=days)).strftime("%Y%m%d")

    rows = (
        db.query(
            Study.study_date,
            func.sum(Instance.file_size).label("bytes"),
        )
        .join(Series, Series.study_id == Study.id)
        .join(Instance, Instance.series_id == Series.id)
        .filter(Study.study_date >= start)
        .group_by(Study.study_date)
        .order_by(Study.study_date)
        .all()
    )

    result = {}
    for i in range(days + 1):
        d = (date.today() - timedelta(days=days - i)).strftime("%Y%m%d")
        result[d] = 0
    for row in rows:
        if row.study_date:
            result[row.study_date] = round((row.bytes or 0) / (1024**3), 3)

    # Make cumulative
    running = 0.0
    cumulative = []
    for d, gb in sorted(result.items()):
        running += gb
        cumulative.append({"date": d, "gb": round(running, 3)})

    return cumulative
