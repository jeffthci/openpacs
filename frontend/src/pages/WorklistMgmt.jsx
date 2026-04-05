// src/pages/WorklistMgmt.jsx
// ─────────────────────────────────────────────────────────────────
// Modality Worklist management — create, view, and manage
// scheduled procedures. The MWL SCP serves these to modalities.

import { useState, useEffect } from "react";
import { ModalityBadge } from "../components/StudyActions";
import api from "../lib/api";

const PRIORITIES = ["ROUTINE", "URGENT", "STAT"];
const MODALITIES = ["CT", "MR", "CR", "DX", "US", "NM", "PT", "MG", "XA", "RF", "SC"];

const today = () => new Date().toISOString().slice(0, 10).replace(/-/g, "");

function WorklistForm({ onCreated, onCancel }) {
  const [form, setForm] = useState({
    patient_name: "", patient_id: "", date_of_birth: "", sex: "M",
    study_description: "", procedure_description: "",
    modality: "CT", scheduled_date: today(), scheduled_time: "080000",
    station_ae_title: "", priority: "ROUTINE",
    referring_physician: "", notes: "",
  });
  const [saving, setSaving] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const save = async () => {
    if (!form.patient_name || !form.patient_id) return alert("Patient name and ID required");
    setSaving(true);
    try {
      await api.post("/worklist", form);
      onCreated();
    } catch (e) {
      alert(e.response?.data?.detail || "Error creating worklist item");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="wl-form">
      <h3>New Scheduled Procedure</h3>
      <div className="wl-form-grid">
        <div>
          <label>Patient Name *</label>
          <input value={form.patient_name} onChange={e => set("patient_name", e.target.value)} placeholder="Last^First^Middle" />
        </div>
        <div>
          <label>Patient ID *</label>
          <input value={form.patient_id} onChange={e => set("patient_id", e.target.value)} />
        </div>
        <div>
          <label>Date of Birth (YYYYMMDD)</label>
          <input value={form.date_of_birth} onChange={e => set("date_of_birth", e.target.value)} placeholder="19800101" />
        </div>
        <div>
          <label>Sex</label>
          <select value={form.sex} onChange={e => set("sex", e.target.value)}>
            <option value="M">M</option><option value="F">F</option><option value="O">O</option>
          </select>
        </div>
        <div>
          <label>Modality</label>
          <select value={form.modality} onChange={e => set("modality", e.target.value)}>
            {MODALITIES.map(m => <option key={m}>{m}</option>)}
          </select>
        </div>
        <div>
          <label>Priority</label>
          <select value={form.priority} onChange={e => set("priority", e.target.value)}>
            {PRIORITIES.map(p => <option key={p}>{p}</option>)}
          </select>
        </div>
        <div>
          <label>Scheduled Date (YYYYMMDD)</label>
          <input value={form.scheduled_date} onChange={e => set("scheduled_date", e.target.value)} />
        </div>
        <div>
          <label>Scheduled Time (HHMMSS)</label>
          <input value={form.scheduled_time} onChange={e => set("scheduled_time", e.target.value)} placeholder="090000" />
        </div>
        <div className="wl-full">
          <label>Study / Procedure Description</label>
          <input value={form.procedure_description} onChange={e => set("procedure_description", e.target.value)} placeholder="CHEST CT W CONTRAST" />
        </div>
        <div>
          <label>Station AE Title</label>
          <input value={form.station_ae_title} onChange={e => set("station_ae_title", e.target.value)} placeholder="CT_SCANNER1" />
        </div>
        <div>
          <label>Referring Physician</label>
          <input value={form.referring_physician} onChange={e => set("referring_physician", e.target.value)} />
        </div>
        <div className="wl-full">
          <label>Notes</label>
          <input value={form.notes} onChange={e => set("notes", e.target.value)} />
        </div>
      </div>
      <div className="wl-form-actions">
        <button className="btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="btn-primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Create Worklist Item"}
        </button>
      </div>
    </div>
  );
}

export default function WorklistMgmt() {
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [filter, setFilter]   = useState({ name: "", modality: "", date: "", overdue: false });

  const fetchItems = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter.name)     params.set("patient_name", filter.name);
      if (filter.modality) params.set("modality",     filter.modality);
      if (filter.date)     params.set("scheduled_date", filter.date.replace(/-/g, ""));
      const r = await api.get(`/worklist?${params}`);
      setItems(r.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchItems(); }, []);

  const complete = async (id) => {
    await api.post(`/worklist/${id}/complete`);
    fetchItems();
  };

  const cancel = async (id) => {
    if (!confirm("Cancel this scheduled procedure?")) return;
    await api.delete(`/worklist/${id}`);
    fetchItems();
  };

  const priorityColor = p => ({ STAT: "#e74c3c", URGENT: "#f39c12", ROUTINE: "#888" }[p] || "#888");

  return (
    <div className="wl-page">
      <div className="page-header">
        <h1>Modality Worklist</h1>
        <button className="btn-primary" onClick={() => setShowForm(true)}>+ New Procedure</button>
      </div>

      {showForm && (
        <WorklistForm onCreated={() => { setShowForm(false); fetchItems(); }} onCancel={() => setShowForm(false)} />
      )}

      <div className="wl-filters">
        <input placeholder="Patient name…" value={filter.name}
          onChange={e => setFilter(f => ({ ...f, name: e.target.value }))} />
        <select value={filter.modality} onChange={e => setFilter(f => ({ ...f, modality: e.target.value }))}>
          <option value="">All modalities</option>
          {MODALITIES.map(m => <option key={m}>{m}</option>)}
        </select>
        <input type="date" value={filter.date.slice(0,10)}
          onChange={e => setFilter(f => ({ ...f, date: e.target.value }))} />
        <button className="btn-sm" onClick={fetchItems}>Search</button>
      </div>

      {loading ? (
        <div className="page-loading">Loading…</div>
      ) : (
        <table className="wl-table">
          <thead>
            <tr>
              <th>Patient</th><th>ID</th><th>Modality</th>
              <th>Procedure</th><th>Scheduled</th><th>Priority</th>
              <th>Station</th><th></th>
            </tr>
          </thead>
          <tbody>
            {items.map(item => (
              <tr key={item.id}>
                <td>{item.patient_name}</td>
                <td className="mono">{item.patient_id}</td>
                <td><ModalityBadge modality={item.modality} size="sm" /></td>
                <td>{item.procedure_description || item.study_description || "—"}</td>
                <td className="mono">{item.scheduled_date} {item.scheduled_time}</td>
                <td><span style={{ color: priorityColor(item.priority), fontSize: 12 }}>{item.priority}</span></td>
                <td className="mono">{item.station_ae_title || "—"}</td>
                <td>
                  <button className="btn-sm" onClick={() => complete(item.id)}>✓ Done</button>
                  <button className="btn-danger-sm" onClick={() => cancel(item.id)}>Cancel</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={8} style={{ textAlign: "center", color: "#668", padding: 20 }}>
                No pending procedures
              </td></tr>
            )}
          </tbody>
        </table>
      )}

      <style>{`
        .wl-page { padding:24px; max-width:1200px; margin:0 auto; }
        .page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
        .page-header h1 { margin:0; font-size:22px; }
        .wl-filters { display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; }
        .wl-filters input, .wl-filters select { background:#1e2436; border:1px solid #2a2f3e; border-radius:5px; color:#ccc; padding:7px 10px; font-size:13px; }
        .wl-table { width:100%; border-collapse:collapse; font-size:13px; }
        .wl-table th { text-align:left; padding:8px 10px; border-bottom:1px solid #2a2f3e; color:#668; font-weight:500; }
        .wl-table td { padding:8px 10px; border-bottom:1px solid #1a1f2e; vertical-align:middle; }
        .wl-table tr:hover td { background:rgba(255,255,255,.02); }
        .mono { font-family:monospace; font-size:12px; color:#9aa; }
        .wl-form { background:#1e2436; border-radius:8px; padding:20px; margin-bottom:20px; border:1px solid #2a2f3e; }
        .wl-form h3 { margin:0 0 16px; font-size:16px; }
        .wl-form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
        .wl-full { grid-column:span 2; }
        .wl-form-grid label { display:block; font-size:11px; color:#668; margin-bottom:4px; }
        .wl-form-grid input, .wl-form-grid select { width:100%; background:#111; border:1px solid #333; border-radius:5px; color:#ccc; padding:7px 10px; font-size:13px; box-sizing:border-box; }
        .wl-form-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:16px; }
        .btn-primary { background:#4a9eff; color:#fff; border:none; border-radius:5px; padding:8px 16px; cursor:pointer; font-size:13px; }
        .btn-secondary { background:#333; color:#ccc; border:none; border-radius:5px; padding:8px 16px; cursor:pointer; font-size:13px; }
        .btn-sm { background:#2a3a4a; color:#4a9eff; border:none; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:12px; margin-right:4px; }
        .btn-danger-sm { background:#3a1a1a; color:#e74c3c; border:none; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:12px; }
        .page-loading { display:flex; align-items:center; justify-content:center; height:30vh; color:#668; }
      `}</style>
    </div>
  );
}
