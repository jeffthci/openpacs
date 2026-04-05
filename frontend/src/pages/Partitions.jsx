// src/pages/Partitions.jsx
// Virtual AE Partition management UI
// Mirrors ClearCanvas ImageServer's partition system

import { useState, useEffect } from "react";
import api from "../lib/api";

function PartitionModal({ partition, onSave, onClose }) {
  const [form, setForm] = useState(partition || {
    ae_title: "", description: "", storage_prefix: "",
    storage_quota_gb: "", dicom_port: "",
    accept_any_ae: false, isolated_qido: true, retention_days: "",
  });

  const f = (field) => (e) => setForm(p => ({
    ...p,
    [field]: e.target.type === "checkbox" ? e.target.checked
           : e.target.type === "number"   ? (e.target.value === "" ? "" : parseInt(e.target.value))
           : e.target.value
  }));

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{partition ? `Edit Partition: ${partition.ae_title}` : "New Partition"}</h3>

        <div className="form-grid-2">
          <div>
            <label>AE Title <span className="req">*</span></label>
            <input
              value={form.ae_title}
              onChange={f("ae_title")}
              maxLength={16}
              placeholder="RADIOLOGY"
              disabled={!!partition}
              style={partition ? { opacity: .6 } : {}}
            />
            <small>Max 16 characters, uppercase</small>
          </div>
          <div>
            <label>DICOM Port</label>
            <input type="number" value={form.dicom_port} onChange={f("dicom_port")}
              placeholder="Leave blank to use primary port" />
            <small>Optional dedicated port for this partition</small>
          </div>
        </div>

        <label>Description</label>
        <input value={form.description} onChange={f("description")}
          placeholder="e.g. Radiology department partition" />

        <div className="form-grid-2">
          <div>
            <label>Storage Prefix</label>
            <input value={form.storage_prefix} onChange={f("storage_prefix")}
              placeholder="radiology" />
            <small>Subdirectory under DICOM_STORAGE_PATH</small>
          </div>
          <div>
            <label>Storage Quota (GB)</label>
            <input type="number" value={form.storage_quota_gb} onChange={f("storage_quota_gb")}
              placeholder="No limit" />
          </div>
        </div>

        <div className="form-grid-2">
          <div>
            <label>Retention Days</label>
            <input type="number" value={form.retention_days} onChange={f("retention_days")}
              placeholder="Keep forever" />
            <small>Auto-purge studies older than N days</small>
          </div>
          <div style={{ paddingTop: 28 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input type="checkbox" checked={form.accept_any_ae} onChange={f("accept_any_ae")} />
              Accept from any calling AE
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginTop: 8 }}>
              <input type="checkbox" checked={form.isolated_qido} onChange={f("isolated_qido")} />
              Isolate QIDO-RS queries
            </label>
          </div>
        </div>

        <div className="modal-actions">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={() => onSave(form)}>
            {partition ? "Save Changes" : "Create Partition"}
          </button>
        </div>
      </div>
    </div>
  );
}

function PartitionCard({ partition, onEdit, onDelete, onToggle, stats }) {
  return (
    <div className={`partition-card ${partition.is_active ? "active" : "inactive"}`}>
      <div className="partition-header">
        <div>
          <span className="ae-badge">{partition.ae_title}</span>
          {partition.dicom_port && (
            <span className="port-badge">:{partition.dicom_port}</span>
          )}
        </div>
        <div className="partition-actions">
          <button className="btn-sm" onClick={() => onToggle(partition)}>
            {partition.is_active ? "Disable" : "Enable"}
          </button>
          <button className="btn-sm" onClick={() => onEdit(partition)}>Edit</button>
          <button className="btn-danger-sm" onClick={() => onDelete(partition)}>Delete</button>
        </div>
      </div>

      <p className="partition-desc">{partition.description || <em style={{ color: "#666" }}>No description</em>}</p>

      <div className="partition-stats">
        {stats ? (
          <>
            <span>{stats.studies} studies</span>
            <span>{stats.instances} instances</span>
            <span>{stats.disk_used_gb} GB used{partition.storage_quota_gb ? ` / ${partition.storage_quota_gb} GB` : ""}</span>
          </>
        ) : (
          <span className="loading-text">Loading stats…</span>
        )}
      </div>

      <div className="partition-meta">
        {partition.storage_prefix && (
          <span className="meta-tag">📁 {partition.storage_prefix}</span>
        )}
        {partition.isolated_qido && (
          <span className="meta-tag">🔒 Isolated QIDO</span>
        )}
        {partition.accept_any_ae && (
          <span className="meta-tag">🔓 Open AE</span>
        )}
        {partition.retention_days && (
          <span className="meta-tag">⏱ {partition.retention_days}d retention</span>
        )}
      </div>
    </div>
  );
}

export default function Partitions() {
  const [partitions, setPartitions] = useState([]);
  const [stats,      setStats]      = useState({});
  const [showModal,  setShowModal]  = useState(false);
  const [editing,    setEditing]    = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState(null);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/partitions");
      setPartitions(data);
      // Fetch stats for each partition
      const statsMap = {};
      await Promise.allSettled(
        data.map(async p => {
          try {
            const r = await api.get(`/partitions/${p.ae_title}/stats`);
            statsMap[p.ae_title] = r.data;
          } catch {}
        })
      );
      setStats(statsMap);
    } catch (e) {
      setError("Failed to load partitions");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const handleSave = async (data) => {
    try {
      if (editing) {
        await api.put(`/partitions/${editing.ae_title}`, data);
      } else {
        await api.post("/partitions", { ...data, ae_title: data.ae_title.toUpperCase() });
      }
      setShowModal(false);
      setEditing(null);
      fetchAll();
    } catch (e) {
      alert(e.response?.data?.detail || "Error saving partition");
    }
  };

  const handleDelete = async (partition) => {
    if (!confirm(`Delete partition ${partition.ae_title}? This cannot be undone.`)) return;
    try {
      await api.delete(`/partitions/${partition.ae_title}`);
      fetchAll();
    } catch (e) {
      alert(e.response?.data?.detail || "Cannot delete partition");
    }
  };

  const handleToggle = async (partition) => {
    await api.post(`/partitions/${partition.ae_title}/activate`);
    fetchAll();
  };

  if (loading) return <div className="page-loading">Loading partitions…</div>;
  if (error)   return <div className="page-error">{error}</div>;

  return (
    <div className="partitions-page">
      <div className="page-header">
        <div>
          <h1>Virtual AE Partitions</h1>
          <p className="page-subtitle">
            Logical separation of studies within one server. Each partition has its own
            AE title, storage path, and access controls.
          </p>
        </div>
        <button className="btn-primary" onClick={() => { setEditing(null); setShowModal(true); }}>
          + New Partition
        </button>
      </div>

      {partitions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">⊞</div>
          <h3>No partitions configured</h3>
          <p>All studies go to the default server partition.<br />
             Create partitions to separate studies by department, modality, or site.</p>
          <button className="btn-primary" onClick={() => setShowModal(true)}>
            Create First Partition
          </button>
        </div>
      ) : (
        <div className="partition-grid">
          {partitions.map(p => (
            <PartitionCard
              key={p.ae_title}
              partition={p}
              stats={stats[p.ae_title]}
              onEdit={(pt) => { setEditing(pt); setShowModal(true); }}
              onDelete={handleDelete}
              onToggle={handleToggle}
            />
          ))}
        </div>
      )}

      {showModal && (
        <PartitionModal
          partition={editing}
          onSave={handleSave}
          onClose={() => { setShowModal(false); setEditing(null); }}
        />
      )}

      <style>{`
        .partitions-page { padding:24px; max-width:1100px; margin:0 auto; }
        .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:28px; }
        .page-header h1 { margin:0 0 4px; font-size:22px; }
        .page-subtitle { margin:0; color:#888; font-size:13px; }
        .partition-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:16px; }
        .partition-card { background:#1e2130; border-radius:10px; padding:18px; border:1px solid #2a2f3e; transition:border-color .2s; }
        .partition-card.inactive { opacity:.55; }
        .partition-card:hover { border-color:#3a4055; }
        .partition-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
        .ae-badge { background:#1a3a6a; color:#4a9eff; font-family:monospace; font-size:15px; font-weight:600; padding:4px 10px; border-radius:5px; }
        .port-badge { background:#1a2a3a; color:#888; font-family:monospace; font-size:12px; padding:4px 6px; border-radius:4px; margin-left:6px; }
        .partition-actions { display:flex; gap:6px; }
        .partition-desc { font-size:13px; color:#aaa; margin:0 0 12px; }
        .partition-stats { display:flex; gap:16px; font-size:12px; color:#6a7d9e; margin-bottom:10px; }
        .partition-meta { display:flex; flex-wrap:wrap; gap:6px; }
        .meta-tag { background:#22283a; color:#8899aa; font-size:11px; padding:3px 8px; border-radius:10px; }
        .loading-text { color:#555; font-style:italic; }
        .empty-state { text-align:center; padding:60px 20px; color:#888; }
        .empty-icon { font-size:48px; margin-bottom:16px; opacity:.4; }
        .empty-state h3 { margin:0 0 8px; color:#aaa; }
        .empty-state p { margin:0 0 20px; line-height:1.6; }
        .form-grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
        .modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,.7); display:flex; align-items:center; justify-content:center; z-index:1000; }
        .modal { background:#1a1f2e; border-radius:10px; padding:24px; width:560px; max-width:95vw; max-height:90vh; overflow-y:auto; }
        .modal h3 { margin:0 0 20px; font-size:17px; }
        .modal label { display:block; font-size:12px; color:#888; margin:12px 0 4px; }
        .modal small { color:#555; font-size:11px; }
        .modal input { width:100%; background:#111; border:1px solid #333; border-radius:5px; color:#fff; padding:8px 10px; font-size:13px; box-sizing:border-box; }
        .req { color:#e74c3c; }
        .modal-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:24px; }
        .btn-primary { background:#4a9eff; color:#fff; border:none; border-radius:5px; padding:8px 16px; cursor:pointer; font-size:13px; }
        .btn-secondary { background:#333; color:#ccc; border:none; border-radius:5px; padding:8px 16px; cursor:pointer; font-size:13px; }
        .btn-sm { background:#2a3a4a; color:#4a9eff; border:none; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:12px; }
        .btn-danger-sm { background:#3a1a1a; color:#e74c3c; border:none; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:12px; }
        .page-loading, .page-error { display:flex; align-items:center; justify-content:center; height:50vh; font-size:16px; color:#888; }
      `}</style>
    </div>
  );
}
