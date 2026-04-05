// src/pages/Admin.jsx
// ─────────────────────────────────────────────────────────────────
// Admin dashboard: server stats, storage management,
// routing rules, and work queue monitor.

import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";

// ── Sub-components ────────────────────────────────────────────────

function StatCard({ label, value, sub, color = "#4a9eff" }) {
  return (
    <div className="stat-card" style={{ borderTop: `3px solid ${color}` }}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function StorageBar({ used, total }) {
  const pct = total > 0 ? Math.round((used / total) * 100) : 0;
  const color = pct > 90 ? "#e74c3c" : pct > 75 ? "#f39c12" : "#2ecc71";
  return (
    <div className="storage-bar-wrap">
      <div className="storage-bar-track">
        <div className="storage-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="storage-bar-label">{pct}%</span>
    </div>
  );
}

function Section({ title, children, action }) {
  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </div>
  );
}

// ── Routing Rule Editor modal ─────────────────────────────────────

function RuleModal({ rule, onSave, onClose }) {
  const [form, setForm] = useState(
    rule || {
      name: "", description: "", priority: 100,
      is_active: true, stop_on_match: true,
      conditions: {}, destinations: [],
    }
  );
  const [condKey, setCondKey]   = useState("");
  const [condVal, setCondVal]   = useState("");
  const [destForm, setDestForm] = useState({ ae_title: "", host: "", port: 104, description: "" });

  const addCondition = () => {
    if (!condKey) return;
    setForm(f => ({ ...f, conditions: { ...f.conditions, [condKey]: condVal } }));
    setCondKey(""); setCondVal("");
  };

  const removeCondition = (k) => {
    const c = { ...form.conditions };
    delete c[k];
    setForm(f => ({ ...f, conditions: c }));
  };

  const addDest = () => {
    if (!destForm.ae_title || !destForm.host) return;
    setForm(f => ({ ...f, destinations: [...f.destinations, { ...destForm }] }));
    setDestForm({ ae_title: "", host: "", port: 104, description: "" });
  };

  const removeDest = (i) =>
    setForm(f => ({ ...f, destinations: f.destinations.filter((_, idx) => idx !== i) }));

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{rule ? "Edit Routing Rule" : "New Routing Rule"}</h3>

        <label>Name</label>
        <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />

        <label>Description</label>
        <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />

        <div className="row-2">
          <div>
            <label>Priority (lower = first)</label>
            <input type="number" value={form.priority}
              onChange={e => setForm(f => ({ ...f, priority: parseInt(e.target.value) || 100 }))} />
          </div>
          <div style={{ display: "flex", gap: 16, marginTop: 28, alignItems: "center" }}>
            <label>
              <input type="checkbox" checked={form.is_active}
                onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))} />
              &nbsp;Active
            </label>
            <label>
              <input type="checkbox" checked={form.stop_on_match}
                onChange={e => setForm(f => ({ ...f, stop_on_match: e.target.checked }))} />
              &nbsp;Stop on match
            </label>
          </div>
        </div>

        <label>Conditions</label>
        <div className="conditions-list">
          {Object.entries(form.conditions).map(([k, v]) => (
            <div key={k} className="condition-tag">
              <span>{k} = {v}</span>
              <button onClick={() => removeCondition(k)}>×</button>
            </div>
          ))}
        </div>
        <div className="row-3">
          <select value={condKey} onChange={e => setCondKey(e.target.value)}>
            <option value="">-- key --</option>
            <option value="modality">modality</option>
            <option value="calling_ae">calling_ae</option>
            <option value="study_description_contains">study_description_contains</option>
            <option value="accession_prefix">accession_prefix</option>
            <option value="body_part">body_part</option>
          </select>
          <input placeholder="value" value={condVal} onChange={e => setCondVal(e.target.value)} />
          <button className="btn-sm" onClick={addCondition}>Add</button>
        </div>

        <label>Destinations</label>
        {form.destinations.map((d, i) => (
          <div key={i} className="dest-row">
            <span>{d.ae_title} @ {d.host}:{d.port}</span>
            <button onClick={() => removeDest(i)}>×</button>
          </div>
        ))}
        <div className="row-4">
          <input placeholder="AE Title" value={destForm.ae_title}
            onChange={e => setDestForm(f => ({ ...f, ae_title: e.target.value }))} />
          <input placeholder="Host / IP" value={destForm.host}
            onChange={e => setDestForm(f => ({ ...f, host: e.target.value }))} />
          <input type="number" placeholder="Port" value={destForm.port}
            onChange={e => setDestForm(f => ({ ...f, port: parseInt(e.target.value) || 104 }))}
            style={{ width: 80 }} />
          <button className="btn-sm" onClick={addDest}>Add</button>
        </div>

        <div className="modal-actions">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={() => onSave(form)}>
            {rule ? "Save Changes" : "Create Rule"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main Admin page ───────────────────────────────────────────────

export default function Admin() {
  const navigate = useNavigate();
  const [stats,       setStats]       = useState(null);
  const [filesystems, setFilesystems] = useState([]);
  const [rules,       setRules]       = useState([]);
  const [queueStatus, setQueueStatus] = useState(null);
  const [showRuleModal, setShowRuleModal] = useState(false);
  const [editingRule,   setEditingRule]   = useState(null);
  const [fsPath,  setFsPath]  = useState("");
  const [fsLabel, setFsLabel] = useState("");
  const [fsTier,  setFsTier]  = useState("primary");
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [s, fs, r, q] = await Promise.all([
        api.get("/admin/stats"),
        api.get("/admin/filesystems"),
        api.get("/admin/routing/rules"),
        api.get("/admin/queue/status"),
      ]);
      setStats(s.data);
      setFilesystems(fs.data);
      setRules(r.data);
      setQueueStatus(q.data);
    } catch (e) {
      setError("Failed to load admin data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const addFilesystem = async () => {
    if (!fsPath) return;
    try {
      await api.post("/admin/filesystems", { path: fsPath, label: fsLabel, tier: fsTier });
      setFsPath(""); setFsLabel("");
      fetchAll();
    } catch (e) {
      alert(e.response?.data?.detail || "Error adding filesystem");
    }
  };

  const removeFilesystem = async (id) => {
    if (!confirm("Remove this storage root?")) return;
    await api.delete(`/admin/filesystems/${id}`);
    fetchAll();
  };

  const saveRule = async (data) => {
    if (editingRule) {
      await api.put(`/admin/routing/rules/${editingRule.id}`, data);
    } else {
      await api.post("/admin/routing/rules", data);
    }
    setShowRuleModal(false);
    setEditingRule(null);
    fetchAll();
  };

  const deleteRule = async (id) => {
    if (!confirm("Delete this routing rule?")) return;
    await api.delete(`/admin/routing/rules/${id}`);
    fetchAll();
  };

  const toggleRule = async (rule) => {
    await api.put(`/admin/routing/rules/${rule.id}`, { ...rule, is_active: !rule.is_active });
    fetchAll();
  };

  if (loading) return <div className="page-loading">Loading admin panel…</div>;
  if (error)   return <div className="page-error">{error}</div>;

  return (
    <div className="admin-page">
      <div className="page-header">
        <h1>Server Administration</h1>
        <button className="btn-secondary" onClick={() => navigate("/")}>← Worklist</button>
      </div>

      {/* ── Stats ─────────────────────────────────────────────────── */}
      {stats && (
        <div className="stats-grid">
          <StatCard label="Patients"  value={stats.patients.toLocaleString()}  color="#4a9eff" />
          <StatCard label="Studies"   value={stats.studies.toLocaleString()}   color="#9b59b6" />
          <StatCard label="Series"    value={stats.series.toLocaleString()}    color="#2ecc71" />
          <StatCard label="Instances" value={stats.instances.toLocaleString()} color="#e67e22" />
          <StatCard
            label="Storage"
            value={`${stats.storage.used_gb} GB used`}
            sub={`${stats.storage.free_gb} GB free of ${stats.storage.total_gb} GB`}
            color={stats.storage.percent > 85 ? "#e74c3c" : "#1abc9c"}
          />
          <StatCard
            label="AE Title"
            value={stats.server.ae_title}
            sub={`DICOM port ${stats.server.dicom_port}`}
            color="#95a5a6"
          />
        </div>
      )}

      {/* ── Work queue ────────────────────────────────────────────── */}
      <Section title="Work Queue">
        <div className={`queue-status ${queueStatus?.status === "ok" ? "ok" : "warn"}`}>
          {queueStatus?.status === "ok" ? (
            <>
              <span className="dot green" /> Workers online ({queueStatus.workers?.length || 0})
              &nbsp;·&nbsp; Active tasks: <strong>{queueStatus.active}</strong>
              &nbsp;·&nbsp; Queued: <strong>{queueStatus.reserved}</strong>
            </>
          ) : (
            <>
              <span className="dot red" /> Celery workers offline —
              ingestion running synchronously. Start with:
              <code> celery -A services.work_queue worker -Q high,default</code>
            </>
          )}
        </div>
        <button className="btn-sm" onClick={async () => {
          await api.post("/admin/queue/retry-failed");
          alert("Re-queued staged files");
        }}>
          Retry Failed Ingests
        </button>
      </Section>

      {/* ── Storage filesystems ───────────────────────────────────── */}
      <Section
        title="Storage Filesystems"
        action={<small style={{ color: "#888" }}>
          Multiple storage roots enable tiered archival
        </small>}
      >
        <table className="admin-table">
          <thead>
            <tr>
              <th>Path</th><th>Label</th><th>Tier</th>
              <th>Usage</th><th>Free</th><th></th>
            </tr>
          </thead>
          <tbody>
            {filesystems.map(fs => (
              <tr key={fs.id}>
                <td><code>{fs.path}</code></td>
                <td>{fs.label || "—"}</td>
                <td><span className={`tier-badge ${fs.tier}`}>{fs.tier}</span></td>
                <td style={{ minWidth: 160 }}>
                  <StorageBar used={fs.used_bytes} total={fs.total_bytes} />
                </td>
                <td>{(fs.available_bytes / 1024**3).toFixed(1)} GB</td>
                <td>
                  <button className="btn-danger-sm" onClick={() => removeFilesystem(fs.id)}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
            {filesystems.length === 0 && (
              <tr><td colSpan={6} style={{ color: "#888", textAlign: "center" }}>
                Using default DICOM_STORAGE_PATH from .env
              </td></tr>
            )}
          </tbody>
        </table>

        <div className="add-fs-form">
          <input placeholder="/mnt/storage/path" value={fsPath}
            onChange={e => setFsPath(e.target.value)} />
          <input placeholder="Label (optional)" value={fsLabel}
            onChange={e => setFsLabel(e.target.value)} />
          <select value={fsTier} onChange={e => setFsTier(e.target.value)}>
            <option value="primary">Primary</option>
            <option value="archive">Archive</option>
          </select>
          <button className="btn-primary" onClick={addFilesystem}>Add Filesystem</button>
        </div>
      </Section>

      {/* ── Routing rules ─────────────────────────────────────────── */}
      <Section
        title="Auto-Routing Rules"
        action={
          <button className="btn-primary" onClick={() => { setEditingRule(null); setShowRuleModal(true); }}>
            + New Rule
          </button>
        }
      >
        <table className="admin-table">
          <thead>
            <tr>
              <th>Pri</th><th>Name</th><th>Conditions</th>
              <th>Destinations</th><th>Active</th><th></th>
            </tr>
          </thead>
          <tbody>
            {rules.map(rule => (
              <tr key={rule.id} className={rule.is_active ? "" : "inactive-row"}>
                <td>{rule.priority}</td>
                <td>{rule.name}</td>
                <td>
                  {Object.entries(rule.conditions || {}).map(([k, v]) => (
                    <span key={k} className="condition-tag small">{k}={v}</span>
                  ))}
                  {Object.keys(rule.conditions || {}).length === 0 &&
                    <span className="condition-tag small gray">catch-all</span>}
                </td>
                <td>
                  {(rule.destinations || []).map((d, i) => (
                    <span key={i} className="dest-tag">{d.ae_title}@{d.host}:{d.port}</span>
                  ))}
                </td>
                <td>
                  <input type="checkbox" checked={rule.is_active}
                    onChange={() => toggleRule(rule)} />
                </td>
                <td className="action-cell">
                  <button className="btn-sm" onClick={() => { setEditingRule(rule); setShowRuleModal(true); }}>
                    Edit
                  </button>
                  <button className="btn-danger-sm" onClick={() => deleteRule(rule.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {rules.length === 0 && (
              <tr><td colSpan={6} style={{ color: "#888", textAlign: "center" }}>
                No routing rules configured — all studies stay local
              </td></tr>
            )}
          </tbody>
        </table>
      </Section>

      {/* ── Rule modal ────────────────────────────────────────────── */}
      {showRuleModal && (
        <RuleModal
          rule={editingRule}
          onSave={saveRule}
          onClose={() => { setShowRuleModal(false); setEditingRule(null); }}
        />
      )}

      <style>{`
        .admin-page { padding: 24px; max-width: 1200px; margin: 0 auto; }
        .page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
        .page-header h1 { margin:0; font-size:24px; }
        .stats-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:16px; margin-bottom:32px; }
        .stat-card { background:var(--bg2,#1e2130); border-radius:8px; padding:16px; }
        .stat-value { font-size:22px; font-weight:600; }
        .stat-label { font-size:12px; color:#888; margin-top:4px; text-transform:uppercase; letter-spacing:.5px; }
        .stat-sub { font-size:11px; color:#666; margin-top:2px; }
        .admin-section { background:var(--bg2,#1e2130); border-radius:8px; padding:20px; margin-bottom:24px; }
        .admin-section-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
        .admin-section-header h2 { margin:0; font-size:16px; font-weight:500; }
        .admin-table { width:100%; border-collapse:collapse; font-size:13px; }
        .admin-table th { text-align:left; padding:8px 12px; border-bottom:1px solid #333; color:#888; font-weight:500; }
        .admin-table td { padding:8px 12px; border-bottom:1px solid #222; vertical-align:middle; }
        .admin-table tr:hover td { background:rgba(255,255,255,.03); }
        .inactive-row td { opacity:.45; }
        .action-cell { display:flex; gap:6px; }
        .storage-bar-wrap { display:flex; align-items:center; gap:8px; }
        .storage-bar-track { flex:1; height:6px; background:#333; border-radius:3px; overflow:hidden; }
        .storage-bar-fill { height:100%; border-radius:3px; transition:width .3s; }
        .storage-bar-label { font-size:11px; color:#888; min-width:32px; }
        .tier-badge { padding:2px 8px; border-radius:10px; font-size:11px; text-transform:uppercase; letter-spacing:.5px; }
        .tier-badge.primary { background:#1a3a5c; color:#4a9eff; }
        .tier-badge.archive { background:#2a2a1a; color:#f39c12; }
        .add-fs-form { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }
        .add-fs-form input { flex:1; min-width:150px; }
        .queue-status { padding:10px 14px; border-radius:6px; font-size:13px; margin-bottom:12px; }
        .queue-status.ok   { background:#0d2d1a; border:1px solid #1a5a2a; }
        .queue-status.warn { background:#2d1a0d; border:1px solid #5a2a0d; }
        .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }
        .dot.green { background:#2ecc71; }
        .dot.red   { background:#e74c3c; }
        code { background:#111; padding:1px 6px; border-radius:3px; font-family:monospace; font-size:12px; }
        .condition-tag { display:inline-flex; align-items:center; gap:6px; background:#1a2a3a; border-radius:4px; padding:3px 8px; font-size:12px; margin:2px; }
        .condition-tag button { background:none; border:none; color:#888; cursor:pointer; font-size:14px; line-height:1; }
        .condition-tag.small { font-size:11px; padding:2px 6px; }
        .condition-tag.gray { background:#222; color:#666; }
        .dest-tag { display:inline-block; background:#1a2d1a; border-radius:4px; padding:2px 6px; font-size:11px; margin:2px; color:#4ecf7a; }
        .dest-row { display:flex; justify-content:space-between; align-items:center; padding:4px 8px; background:#1a1f2e; border-radius:4px; margin-bottom:4px; }
        .dest-row button { background:none; border:none; color:#e74c3c; cursor:pointer; font-size:16px; }
        .modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,.7); display:flex; align-items:center; justify-content:center; z-index:1000; }
        .modal { background:#1a1f2e; border-radius:10px; padding:24px; width:600px; max-width:95vw; max-height:85vh; overflow-y:auto; }
        .modal h3 { margin:0 0 20px; }
        .modal label { display:block; font-size:12px; color:#888; margin:12px 0 4px; }
        .modal input, .modal select { width:100%; background:#111; border:1px solid #333; border-radius:5px; color:#fff; padding:8px 10px; font-size:13px; box-sizing:border-box; }
        .row-2 { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
        .row-3 { display:grid; grid-template-columns:1fr 1fr auto; gap:8px; margin-top:6px; }
        .row-4 { display:grid; grid-template-columns:1fr 1fr 80px auto; gap:8px; margin-top:6px; }
        .conditions-list { display:flex; flex-wrap:wrap; gap:4px; min-height:28px; }
        .modal-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:20px; }
        .btn-primary { background:#4a9eff; color:#fff; border:none; border-radius:5px; padding:8px 16px; cursor:pointer; font-size:13px; }
        .btn-secondary { background:#333; color:#ccc; border:none; border-radius:5px; padding:8px 16px; cursor:pointer; font-size:13px; }
        .btn-sm { background:#2a3a4a; color:#4a9eff; border:none; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:12px; }
        .btn-danger-sm { background:#3a1a1a; color:#e74c3c; border:none; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:12px; }
        .page-loading, .page-error { display:flex; align-items:center; justify-content:center; height:50vh; font-size:16px; color:#888; }
      `}</style>
    </div>
  );
}
