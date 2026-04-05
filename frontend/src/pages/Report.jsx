// src/pages/Report.jsx
// Radiology report editor — create/edit structured reports, export to PDF.

import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../lib/api";

const STATUS_COLORS = {
  draft:     "#f59e0b",
  final:     "#34d399",
  addendum:  "#4a9eff",
  corrected: "#a78bfa",
};

export default function Report() {
  const { uid }               = useParams();
  const navigate              = useNavigate();
  const [study,   setStudy]   = useState(null);
  const [report,  setReport]  = useState(null);
  const [form,    setForm]    = useState({
    clinical_history: "",
    technique:        "",
    findings:         "",
    impression:       "",
    recommendations:  "",
    status:           "draft",
  });
  const [saving,    setSaving]    = useState(false);
  const [exporting, setExporting] = useState(false);
  const [saved,     setSaved]     = useState(false);
  const [error,     setError]     = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const { data: studyData } = await api.get(`/api/studies/${uid}`);
        setStudy(studyData);
        // Load existing report if any
        const { data: reports } = await api.get(`/api/reports?study_id=${uid}`);
        const existing = Array.isArray(reports) ? reports[0] : reports?.items?.[0];
        if (existing) {
          setReport(existing);
          setForm({
            clinical_history: existing.clinical_history || "",
            technique:        existing.technique        || "",
            findings:         existing.findings         || "",
            impression:       existing.impression       || "",
            recommendations:  existing.recommendations  || "",
            status:           existing.status           || "draft",
          });
        }
      } catch (e) {
        setError("Failed to load study");
      }
    };
    load();
  }, [uid]);

  const save = async (status) => {
    setSaving(true); setError(null);
    try {
      const payload = { ...form, study_id: parseInt(uid), status: status || form.status };
      if (report?.id) {
        const { data } = await api.put(`/api/reports/${report.id}`, payload);
        setReport(data);
      } else {
        const { data } = await api.post("/api/reports", payload);
        setReport(data);
      }
      setForm(f => ({ ...f, status: status || f.status }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const exportPDF = async () => {
    if (!report?.id) { alert("Save the report first"); return; }
    setExporting(true);
    try {
      const response = await api.get(`/api/reports/${report.id}/pdf`, { responseType: "blob" });
      const url  = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href     = url;
      link.download = `report_${study?.accession_number || uid}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError("PDF export failed");
    } finally {
      setExporting(false);
    }
  };

  const pt     = study?.patient || {};
  const status = form.status;

  return (
    <div className="report-page">
      <div className="report-header">
        <button className="back-btn" onClick={() => navigate(-1)}>← Study</button>
        <div className="report-title">
          <h1>Radiology Report</h1>
          {study && (
            <span className="report-meta">
              {pt.patient_name} · {study.study_description || "Study"} · {fmtDate(study.study_date)}
            </span>
          )}
        </div>
        <div className="report-status" style={{ color: STATUS_COLORS[status] }}>
          ● {status.charAt(0).toUpperCase() + status.slice(1)}
        </div>
        <div className="report-actions">
          {saved && <span className="saved-badge">✓ Saved</span>}
          <button className="btn-save-draft" onClick={() => save("draft")} disabled={saving}>
            {saving ? "Saving…" : "Save Draft"}
          </button>
          <button className="btn-finalize" onClick={() => save("final")} disabled={saving}>
            Finalize
          </button>
          <button className="btn-pdf" onClick={exportPDF} disabled={exporting}>
            {exporting ? "Exporting…" : "Export PDF"}
          </button>
        </div>
      </div>

      {error && <div className="report-error">{error}</div>}

      <div className="report-body">
        {/* Study info sidebar */}
        <div className="report-sidebar">
          <h3>Study Info</h3>
          {study && <>
            <dl>
              <dt>Patient</dt><dd>{pt.patient_name}</dd>
              <dt>ID</dt>     <dd className="mono">{pt.patient_id}</dd>
              <dt>DOB</dt>    <dd>{fmtDob(pt.date_of_birth)}</dd>
              <dt>Date</dt>   <dd>{fmtDate(study.study_date)}</dd>
              <dt>Modality</dt><dd>{(study.modalities_in_study || []).join(", ")}</dd>
              <dt>Accession</dt><dd className="mono">{study.accession_number}</dd>
            </dl>
            <button
              className="btn-open-viewer"
              onClick={() => navigate(`/viewer/${uid}`)}
            >
              Open Images ↗
            </button>
          </>}
          {report && (
            <>
              <h3 style={{ marginTop: 20 }}>Report History</h3>
              <div className="history-item">
                <span style={{ color: STATUS_COLORS[report.status] }}>
                  {report.status}
                </span>
                <span className="mono">{fmtDateTime(report.updated_at)}</span>
              </div>
              {report.radiologist && (
                <div className="history-item">by {report.radiologist}</div>
              )}
            </>
          )}
        </div>

        {/* Report form */}
        <div className="report-form">
          <Section label="Clinical History" name="clinical_history" form={form} setForm={setForm} rows={3} />
          <Section label="Technique"        name="technique"        form={form} setForm={setForm} rows={2} />
          <Section label="Findings"         name="findings"         form={form} setForm={setForm} rows={10} required />
          <Section label="Impression"       name="impression"       form={form} setForm={setForm} rows={5} required />
          <Section label="Recommendations"  name="recommendations"  form={form} setForm={setForm} rows={3} />
        </div>
      </div>

      <style>{`
        .report-page { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
        .report-header { display: flex; align-items: center; gap: 14px; padding: 12px 20px; border-bottom: 1px solid #2a2f3e; flex-shrink: 0; flex-wrap: wrap; }
        .back-btn { background: none; border: 1px solid #2a2f3e; border-radius: 5px; color: #888; padding: 6px 12px; font-size: 13px; cursor: pointer; }
        .back-btn:hover { color: #ccc; border-color: #4a4f5e; }
        .report-title { flex: 1; }
        .report-title h1 { margin: 0; font-size: 18px; }
        .report-meta { font-size: 12px; color: #666; }
        .report-status { font-size: 13px; font-weight: 600; }
        .report-actions { display: flex; align-items: center; gap: 8px; }
        .saved-badge { font-size: 12px; color: #34d399; }
        .btn-save-draft { background: #1e2330; border: 1px solid #2a2f3e; color: #ccc; padding: 7px 14px; border-radius: 5px; font-size: 13px; cursor: pointer; }
        .btn-finalize   { background: #1a3a2a; color: #34d399; border: none; padding: 7px 14px; border-radius: 5px; font-size: 13px; cursor: pointer; font-weight: 600; }
        .btn-pdf        { background: #1a3a5c; color: #4a9eff; border: none; padding: 7px 14px; border-radius: 5px; font-size: 13px; cursor: pointer; }
        .report-error { background: #2a1818; border: 1px solid #5a2828; border-radius: 6px; padding: 10px 20px; color: #e74c3c; font-size: 13px; flex-shrink: 0; }
        .report-body { display: flex; flex: 1; overflow: hidden; }
        .report-sidebar { width: 240px; flex-shrink: 0; padding: 16px; border-right: 1px solid #2a2f3e; overflow-y: auto; }
        .report-sidebar h3 { font-size: 11px; text-transform: uppercase; color: #666; letter-spacing: .4px; margin: 0 0 10px; }
        dl { margin: 0 0 12px; display: grid; grid-template-columns: auto 1fr; gap: 4px 8px; }
        dt { font-size: 11px; color: #666; }
        dd { font-size: 12px; color: #bbb; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        dd.mono { font-family: monospace; font-size: 11px; }
        .btn-open-viewer { width: 100%; background: #1a3a5c; color: #4a9eff; border: none; border-radius: 5px; padding: 7px; font-size: 12px; cursor: pointer; margin-top: 8px; }
        .history-item { display: flex; justify-content: space-between; font-size: 12px; padding: 4px 0; border-bottom: 1px solid #1e2330; color: #888; }
        .report-form { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
        .report-section label.section-label { display: block; font-size: 12px; color: #888; font-weight: 500; text-transform: uppercase; letter-spacing: .4px; margin-bottom: 6px; }
        .report-section label.section-label .required { color: #e74c3c; margin-left: 3px; }
        .report-section textarea { width: 100%; background: #1e2330; border: 1px solid #2a2f3e; border-radius: 6px; color: #e0e4f0; padding: 10px 12px; font-size: 14px; font-family: inherit; line-height: 1.6; resize: vertical; box-sizing: border-box; outline: none; transition: border-color .2s; }
        .report-section textarea:focus { border-color: #4a9eff; }
      `}</style>
    </div>
  );
}

function Section({ label, name, form, setForm, rows, required }) {
  return (
    <div className="report-section">
      <label className="section-label">
        {label}{required && <span className="required">*</span>}
      </label>
      <textarea
        rows={rows}
        value={form[name]}
        onChange={e => setForm(f => ({ ...f, [name]: e.target.value }))}
        placeholder={`Enter ${label.toLowerCase()}…`}
      />
    </div>
  );
}

function fmtDate(d) {
  if (!d || d.length < 8) return "—";
  if (d.length === 8) return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`;
  return d.slice(0,10);
}
function fmtDob(d) {
  if (!d || d.length < 8) return "—";
  return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`;
}
function fmtDateTime(s) {
  if (!s) return "";
  return new Date(s).toLocaleString();
}
