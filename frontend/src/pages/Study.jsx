// src/pages/Study.jsx
import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../lib/api";

function SeriesCard({ series, studyUID, onClick }) {
  const mod = series.modality || "??";
  const COLORS = { CT:"#4a9eff", MR:"#a78bfa", CR:"#34d399", DX:"#34d399",
                   US:"#fbbf24", NM:"#f87171", PT:"#fb923c", MG:"#e879f9" };
  const color = COLORS[mod] || "#888";
  return (
    <div className="series-card" onClick={onClick}>
      <div className="series-mod" style={{ color, borderColor: color + "44" }}>{mod}</div>
      <div className="series-info">
        <div className="series-desc">{series.series_description || "No description"}</div>
        <div className="series-meta">
          Series {series.series_number ?? "??"} · {series.number_of_series_related_instances ?? 0} images
        </div>
      </div>
      <div className="series-arrow">›</div>
    </div>
  );
}

export default function Study() {
  const { uid }              = useParams();
  const navigate             = useNavigate();
  const [study,   setStudy]  = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]  = useState(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        // Try by numeric id first, then by UID
        const endpoint = isNaN(uid)
          ? `/api/studies?study_uid=${uid}`
          : `/api/studies/${uid}`;
        const { data } = await api.get(endpoint);
        setStudy(Array.isArray(data) ? data[0] : data);
      } catch (e) {
        setError(e.response?.data?.detail || "Study not found");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [uid]);

  if (loading) return <div className="page-loading">Loading study…</div>;
  if (error || !study) return <div className="page-error">{error || "Study not found"}</div>;

  const pt = study.patient || {};
  const seriesList = study.series || [];

  return (
    <div className="study-page">
      {/* Header */}
      <div className="study-header">
        <button className="back-btn" onClick={() => navigate(-1)}>← Back</button>
        <div className="study-title">
          <h1>{pt.patient_name || "Unknown Patient"}</h1>
          <span className="study-date">{fmtDate(study.study_date)}</span>
        </div>
        <div className="study-actions">
          <button className="btn-ohif"
            onClick={() => navigate(`/ohif?studyUID=${study.study_instance_uid}`)}>
            Open in OHIF
          </button>
          <button className="btn-viewer"
            onClick={() => navigate(`/viewer/${study.id}`)}>
            Open Viewer
          </button>
          <button className="btn-report"
            onClick={() => navigate(`/report/${study.id}`)}>
            Report
          </button>
          <button className="btn-burn"
            onClick={() => navigate(`/burn?studyId=${study.id}`)}>
            Burn CD
          </button>
        </div>
      </div>

      <div className="study-body">
        {/* Patient info panel */}
        <div className="info-panel">
          <h3>Patient Information</h3>
          <dl>
            <dt>Name</dt><dd>{pt.patient_name || "—"}</dd>
            <dt>ID</dt><dd className="mono">{pt.patient_id || "—"}</dd>
            <dt>DOB</dt><dd>{fmtDob(pt.date_of_birth)}</dd>
            <dt>Sex</dt><dd>{pt.sex || "—"}</dd>
          </dl>
          <h3>Study Information</h3>
          <dl>
            <dt>Date</dt><dd>{fmtDate(study.study_date)}</dd>
            <dt>Description</dt><dd>{study.study_description || "—"}</dd>
            <dt>Accession</dt><dd className="mono">{study.accession_number || "—"}</dd>
            <dt>Modalities</dt><dd>{(study.modalities_in_study || []).join(", ") || "—"}</dd>
            <dt>Referring Physician</dt><dd>{study.referring_physician || "—"}</dd>
            <dt>Study UID</dt><dd className="mono small">{study.study_instance_uid}</dd>
            {study.partition && <><dt>Partition</dt><dd>{study.partition.ae_title}</dd></>}
          </dl>
        </div>

        {/* Series list */}
        <div className="series-panel">
          <div className="series-header">
            <h3>Series ({seriesList.length})</h3>
            <span className="instance-count">
              {study.number_of_study_related_instances ?? 0} total images
            </span>
          </div>
          <div className="series-list">
            {seriesList.length === 0 && (
              <div className="empty">No series found for this study</div>
            )}
            {seriesList
              .sort((a, b) => (a.series_number ?? 0) - (b.series_number ?? 0))
              .map(s => (
                <SeriesCard
                  key={s.id}
                  series={s}
                  studyUID={study.study_instance_uid}
                  onClick={() => navigate(`/viewer/${study.id}?series=${s.id}`)}
                />
              ))}
          </div>
        </div>
      </div>

      <style>{`
        .study-page { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
        .study-header { display: flex; align-items: center; gap: 16px; padding: 14px 20px; border-bottom: 1px solid #2a2f3e; flex-shrink: 0; flex-wrap: wrap; }
        .back-btn { background: none; border: 1px solid #2a2f3e; border-radius: 5px; color: #888; padding: 6px 12px; font-size: 13px; cursor: pointer; }
        .back-btn:hover { color: #ccc; border-color: #4a4f5e; }
        .study-title { flex: 1; }
        .study-title h1 { margin: 0; font-size: 18px; }
        .study-date { font-size: 13px; color: #666; }
        .study-actions { display: flex; gap: 8px; flex-wrap: wrap; }
        .study-actions button { padding: 7px 14px; border: none; border-radius: 5px; font-size: 13px; cursor: pointer; font-weight: 500; }
        .btn-ohif   { background: #2a1a5c; color: #a78bfa; }
        .btn-viewer { background: #1a3a5c; color: #4a9eff; }
        .btn-report { background: #1a3a2a; color: #34d399; }
        .btn-burn   { background: #3a2a1a; color: #f59e0b; }
        .study-body { display: flex; flex: 1; overflow: hidden; }
        .info-panel { width: 280px; flex-shrink: 0; padding: 20px; border-right: 1px solid #2a2f3e; overflow-y: auto; }
        .info-panel h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .5px; color: #666; margin: 20px 0 10px; }
        .info-panel h3:first-child { margin-top: 0; }
        dl { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; }
        dt { font-size: 11px; color: #666; padding-top: 1px; white-space: nowrap; }
        dd { font-size: 13px; color: #ccc; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        dd.mono { font-family: monospace; font-size: 11px; }
        dd.small { font-size: 10px; }
        .series-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        .series-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 20px; border-bottom: 1px solid #2a2f3e; flex-shrink: 0; }
        .series-header h3 { margin: 0; font-size: 15px; }
        .instance-count { font-size: 12px; color: #666; }
        .series-list { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
        .series-card { display: flex; align-items: center; gap: 14px; background: #1e2330; border: 1px solid #2a2f3e; border-radius: 8px; padding: 14px 16px; cursor: pointer; transition: background .15s, border-color .15s; }
        .series-card:hover { background: #252d42; border-color: #4a9eff44; }
        .series-mod { width: 42px; height: 42px; display: flex; align-items: center; justify-content: center; border-radius: 6px; border: 1px solid; font-weight: 700; font-size: 12px; flex-shrink: 0; }
        .series-info { flex: 1; overflow: hidden; }
        .series-desc { font-size: 14px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .series-meta { font-size: 12px; color: #666; margin-top: 3px; }
        .series-arrow { color: #444; font-size: 20px; }
        .empty { color: #666; text-align: center; padding: 40px; }
        .page-loading, .page-error { display: flex; align-items: center; justify-content: center; height: 50vh; color: #888; font-size: 15px; }
        .page-error { color: #e74c3c; }
      `}</style>
    </div>
  );
}

function fmtDate(d) {
  if (!d) return "—";
  if (d.length === 8) return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`;
  return d.slice(0, 10);
}
function fmtDob(d) {
  if (!d || d.length < 8) return "—";
  return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`;
}
