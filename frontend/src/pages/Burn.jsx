// src/pages/Burn.jsx
// Burn a study to CD or create an ISO file.

import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api from "../lib/api";

export default function Burn() {
  const navigate             = useNavigate();
  const [searchParams]       = useSearchParams();
  const studyIdParam         = searchParams.get("studyId");

  const [study,     setStudy]     = useState(null);
  const [label,     setLabel]     = useState("");
  const [includeViewer, setIncludeViewer] = useState(true);
  const [burning,   setBurning]   = useState(false);
  const [jobId,     setJobId]     = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [error,     setError]     = useState(null);

  useEffect(() => {
    if (!studyIdParam) return;
    api.get(`/api/studies/${studyIdParam}`).then(r => {
      setStudy(r.data);
      const pt = r.data.patient;
      setLabel(`${pt?.patient_id || "PT"}_${r.data.study_date || "STUDY"}`);
    }).catch(() => setError("Study not found"));
  }, [studyIdParam]);

  // Poll job status
  useEffect(() => {
    if (!jobId) return;
    const poll = setInterval(async () => {
      try {
        const { data } = await api.get(`/api/burn/${jobId}`);
        setJobStatus(data);
        if (data.status === "complete" || data.status === "error") {
          clearInterval(poll);
          setBurning(false);
        }
      } catch { clearInterval(poll); }
    }, 2000);
    return () => clearInterval(poll);
  }, [jobId]);

  const startBurn = async () => {
    setError(null);
    setBurning(true);
    try {
      const { data } = await api.post("/api/burn", {
        study_ids:      [parseInt(studyIdParam)],
        volume_label:   label,
        include_viewer: includeViewer,
      });
      setJobId(data.job_id);
      setJobStatus({ status: "queued", progress: 0 });
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to start burn job");
      setBurning(false);
    }
  };

  const downloadISO = () => {
    if (!jobStatus?.iso_path) return;
    window.open(`${import.meta.env.VITE_API_URL || ""}/api/burn/${jobId}/download`, "_blank");
  };

  const pt = study?.patient || {};
  const progress = jobStatus?.progress || 0;

  return (
    <div className="burn-page">
      <div className="page-hdr">
        <button className="back-btn" onClick={() => navigate(-1)}>← Back</button>
        <h1>Burn to CD / Create ISO</h1>
      </div>

      {error && <div className="burn-error">{error}</div>}

      {!jobId ? (
        <div className="burn-form">
          {study ? (
            <div className="study-summary">
              <div className="study-summary-row">
                <span className="label">Patient</span>
                <span>{pt.patient_name} ({pt.patient_id})</span>
              </div>
              <div className="study-summary-row">
                <span className="label">Study Date</span>
                <span>{fmtDate(study.study_date)}</span>
              </div>
              <div className="study-summary-row">
                <span className="label">Description</span>
                <span>{study.study_description || "—"}</span>
              </div>
              <div className="study-summary-row">
                <span className="label">Images</span>
                <span>{study.number_of_study_related_instances ?? "?"} instances</span>
              </div>
            </div>
          ) : (
            <div className="loading-msg">Loading study…</div>
          )}

          <div className="field">
            <label>Volume Label</label>
            <input
              value={label}
              onChange={e => setLabel(e.target.value)}
              maxLength={32}
              placeholder="e.g. PT12345_20250101"
            />
            <span className="field-hint">Used as the CD/ISO volume name (max 32 chars)</span>
          </div>

          <div className="field">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={includeViewer}
                onChange={e => setIncludeViewer(e.target.checked)}
              />
              Include DICOM viewer on disc
            </label>
            <span className="field-hint">Bundles a portable Weasis viewer so images open on any Windows/Mac PC</span>
          </div>

          <button
            className="btn-start-burn"
            onClick={startBurn}
            disabled={burning || !study}
          >
            {burning ? "Starting…" : "Create ISO"}
          </button>
        </div>
      ) : (
        <div className="burn-progress">
          <div className="burn-status-label">
            {jobStatus?.status === "complete" ? "✓ ISO created" :
             jobStatus?.status === "error"    ? "✗ Error"       :
             `${jobStatus?.status || "Building ISO"}…`}
          </div>

          <div className="progress-bar-track">
            <div
              className="progress-bar-fill"
              style={{
                width: `${progress}%`,
                background: jobStatus?.status === "error" ? "#e74c3c" : "#4a9eff"
              }}
            />
          </div>
          <div className="progress-label">{progress}%</div>

          {jobStatus?.status === "error" && (
            <div className="burn-error">{jobStatus.error || "Burn failed"}</div>
          )}

          {jobStatus?.status === "complete" && (
            <div className="burn-complete">
              <div className="complete-msg">
                ISO file ready — {fmtSize(jobStatus.iso_size_bytes)}
              </div>
              <div className="complete-actions">
                <button className="btn-download" onClick={downloadISO}>
                  ⬇ Download ISO
                </button>
                <button className="btn-new" onClick={() => { setJobId(null); setJobStatus(null); }}>
                  Burn Another
                </button>
                <button className="btn-back" onClick={() => navigate("/")}>
                  Back to Worklist
                </button>
              </div>
            </div>
          )}

          {jobStatus?.message && (
            <div className="burn-log">{jobStatus.message}</div>
          )}
        </div>
      )}

      <style>{`
        .burn-page { padding: 24px; max-width: 600px; margin: 0 auto; }
        .page-hdr { display: flex; align-items: center; gap: 14px; margin-bottom: 24px; }
        .page-hdr h1 { margin: 0; font-size: 22px; }
        .back-btn { background: none; border: 1px solid #2a2f3e; border-radius: 5px; color: #888; padding: 6px 12px; font-size: 13px; cursor: pointer; }
        .back-btn:hover { color: #ccc; }
        .burn-error { background: #2a1818; border: 1px solid #5a2828; border-radius: 6px; padding: 10px 14px; color: #e74c3c; font-size: 13px; margin-bottom: 16px; }
        .burn-form { display: flex; flex-direction: column; gap: 20px; }
        .study-summary { background: #1e2330; border-radius: 8px; padding: 16px; }
        .study-summary-row { display: flex; gap: 12px; padding: 5px 0; border-bottom: 1px solid #2a2f3e; font-size: 13px; }
        .study-summary-row:last-child { border: none; }
        .study-summary-row .label { width: 100px; color: #666; flex-shrink: 0; }
        .field { display: flex; flex-direction: column; gap: 6px; }
        .field label { font-size: 12px; color: #888; font-weight: 500; }
        .field input[type="text"] { background: #1e2330; border: 1px solid #2a2f3e; border-radius: 6px; color: #ddd; padding: 9px 12px; font-size: 13px; outline: none; }
        .field input[type="text"]:focus { border-color: #4a9eff; }
        .field-hint { font-size: 11px; color: #555; }
        .checkbox-label { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #ccc; cursor: pointer; }
        .btn-start-burn { background: #f59e0b; color: #000; border: none; border-radius: 6px; padding: 12px; font-size: 14px; font-weight: 700; cursor: pointer; width: 100%; }
        .btn-start-burn:disabled { opacity: .5; cursor: default; }
        .burn-progress { display: flex; flex-direction: column; gap: 16px; }
        .burn-status-label { font-size: 15px; font-weight: 500; }
        .progress-bar-track { height: 8px; background: #2a2f3e; border-radius: 4px; overflow: hidden; }
        .progress-bar-fill { height: 100%; border-radius: 4px; transition: width .5s; }
        .progress-label { font-size: 12px; color: #666; }
        .burn-complete { background: #0a2a1a; border: 1px solid #1a5a2a; border-radius: 8px; padding: 16px; }
        .complete-msg { color: #34d399; font-size: 14px; margin-bottom: 12px; }
        .complete-actions { display: flex; gap: 10px; flex-wrap: wrap; }
        .btn-download { background: #34d399; color: #000; border: none; border-radius: 5px; padding: 8px 16px; font-size: 13px; cursor: pointer; font-weight: 700; }
        .btn-new, .btn-back { background: #1e2330; border: 1px solid #2a2f3e; color: #ccc; border-radius: 5px; padding: 8px 16px; font-size: 13px; cursor: pointer; }
        .burn-log { font-family: monospace; font-size: 11px; color: #666; background: #0d1117; padding: 10px; border-radius: 5px; }
        .loading-msg { color: #666; padding: 12px; text-align: center; }
      `}</style>
    </div>
  );
}

function fmtDate(d) {
  if (!d || d.length < 8) return "—";
  if (d.length === 8) return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`;
  return d.slice(0,10);
}
function fmtSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024*1024) return `${(bytes/1024).toFixed(1)} KB`;
  return `${(bytes/1024/1024).toFixed(0)} MB`;
}
