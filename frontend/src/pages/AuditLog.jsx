// src/pages/AuditLog.jsx
// HIPAA audit log viewer — admin only
// Shows all PHI access, auth events, and admin changes
// with hash chain integrity verification

import { useState, useEffect, useCallback } from "react";
import api from "../lib/api";

const EVENT_COLORS = {
  "auth.login":    "#2ecc71",
  "auth.logout":   "#95a5a6",
  "auth.":         "#f39c12",
  "phi.":          "#4a9eff",
  "transfer.":     "#9b59b6",
  "admin.":        "#e67e22",
  "security.":     "#e74c3c",
};

function eventColor(type) {
  for (const [prefix, color] of Object.entries(EVENT_COLORS)) {
    if (type.startsWith(prefix)) return color;
  }
  return "#888";
}

function outcomeColor(outcome) {
  return outcome === "success" ? "#2ecc71" : "#e74c3c";
}

function formatTime(ts) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

function EventBadge({ type }) {
  const short = type.split(".").slice(-1)[0];
  return (
    <span style={{
      background: eventColor(type) + "22",
      color: eventColor(type),
      border: `1px solid ${eventColor(type)}44`,
      borderRadius: 4, padding: "2px 7px", fontSize: 11, fontFamily: "monospace",
      whiteSpace: "nowrap",
    }}>
      {short}
    </span>
  );
}

export default function AuditLog() {
  const [logs,      setLogs]      = useState([]);
  const [total,     setTotal]     = useState(0);
  const [integrity, setIntegrity] = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [page,      setPage]      = useState(0);
  const [filters,   setFilters]   = useState({
    event_type: "", username: "", resource_id: "",
    start_date: "", end_date: "",
  });
  const LIMIT = 50;

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit",  LIMIT);
      params.set("offset", page * LIMIT);
      if (filters.event_type) params.set("event_type", filters.event_type);
      if (filters.username)   params.set("username",   filters.username);
      if (filters.resource_id) params.set("resource_id", filters.resource_id);
      if (filters.start_date) params.set("start_date", filters.start_date);
      if (filters.end_date)   params.set("end_date",   filters.end_date + "T23:59:59");

      const [logsRes, countRes] = await Promise.all([
        api.get(`/audit/logs?${params}`),
        api.get(`/audit/logs/count?${new URLSearchParams({
          event_type: filters.event_type || undefined,
          username:   filters.username   || undefined,
        })}`),
      ]);
      setLogs(logsRes.data);
      setTotal(countRes.data.count);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [page, filters]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const checkIntegrity = async () => {
    try {
      const { data } = await api.get("/audit/integrity?last_n=5000");
      setIntegrity(data);
    } catch (e) {
      setIntegrity({ status: "ERROR", detail: e.message });
    }
  };

  const f = (field) => (e) => {
    setFilters(p => ({ ...p, [field]: e.target.value }));
    setPage(0);
  };

  const totalPages = Math.ceil(total / LIMIT);

  return (
    <div className="audit-page">
      <div className="page-header">
        <div>
          <h1>Audit Log</h1>
          <p className="page-subtitle">
            HIPAA §164.312(b) — All PHI access and administrative activity.
            Minimum 6-year retention required.
          </p>
        </div>
        <button
          className={`btn-integrity ${integrity ? (integrity.status === "ok" ? "ok" : "fail") : ""}`}
          onClick={checkIntegrity}
        >
          {integrity
            ? integrity.status === "ok"
              ? `✓ ${integrity.checked} entries verified`
              : `⚠ ${integrity.broken} violations`
            : "Verify Integrity"}
        </button>
      </div>

      {integrity && (
        <div className={`integrity-banner ${integrity.status === "ok" ? "ok" : "fail"}`}>
          {integrity.status === "ok"
            ? `Hash chain intact — ${integrity.checked} entries verified, ${integrity.intact} unmodified.`
            : `INTEGRITY VIOLATION — ${integrity.broken} tampered entries detected out of ${integrity.checked} checked.`
          }
        </div>
      )}

      {/* ── Filters ─────────────────────────────────────────── */}
      <div className="filter-bar">
        <input
          placeholder="Event type filter (e.g. phi, auth, admin)"
          value={filters.event_type}
          onChange={f("event_type")}
          className="filter-input"
        />
        <input
          placeholder="Username"
          value={filters.username}
          onChange={f("username")}
          className="filter-input"
          style={{ width: 150 }}
        />
        <input
          placeholder="Resource ID"
          value={filters.resource_id}
          onChange={f("resource_id")}
          className="filter-input"
          style={{ width: 200 }}
        />
        <input
          type="date"
          value={filters.start_date}
          onChange={f("start_date")}
          className="filter-input"
          style={{ width: 140 }}
        />
        <span style={{ color: "#555" }}>–</span>
        <input
          type="date"
          value={filters.end_date}
          onChange={f("end_date")}
          className="filter-input"
          style={{ width: 140 }}
        />
        <button className="btn-secondary" onClick={() => {
          setFilters({ event_type: "", username: "", resource_id: "", start_date: "", end_date: "" });
          setPage(0);
        }}>Clear</button>
      </div>

      <div className="result-count">
        {total.toLocaleString()} entries
        {page > 0 && ` — page ${page + 1} of ${totalPages}`}
      </div>

      {/* ── Log table ────────────────────────────────────────── */}
      <div className="log-table-wrap">
        <table className="log-table">
          <thead>
            <tr>
              <th style={{ width: 170 }}>Time</th>
              <th style={{ width: 130 }}>Event</th>
              <th style={{ width: 120 }}>User</th>
              <th style={{ width: 100 }}>IP</th>
              <th style={{ width: 90 }}>Resource</th>
              <th style={{ width: 200 }}>Resource ID</th>
              <th style={{ width: 80 }}>Outcome</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} style={{ textAlign: "center", color: "#555", padding: 20 }}>
                Loading…
              </td></tr>
            ) : logs.length === 0 ? (
              <tr><td colSpan={8} style={{ textAlign: "center", color: "#555", padding: 20 }}>
                No entries match the current filters
              </td></tr>
            ) : logs.map(log => (
              <tr key={log.id} className={log.outcome !== "success" ? "row-fail" : ""}>
                <td className="mono">{formatTime(log.event_time)}</td>
                <td><EventBadge type={log.event_type} /></td>
                <td className="mono">{log.username || "—"}</td>
                <td className="mono">{log.ip_address || "—"}</td>
                <td>{log.resource_type || "—"}</td>
                <td className="mono truncate" title={log.resource_id}>{log.resource_id || "—"}</td>
                <td>
                  <span style={{ color: outcomeColor(log.outcome), fontSize: 12 }}>
                    {log.outcome}
                  </span>
                </td>
                <td className="desc">{log.description || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Pagination ───────────────────────────────────────── */}
      {totalPages > 1 && (
        <div className="pagination">
          <button className="btn-sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>
            ← Prev
          </button>
          <span>{page + 1} / {totalPages}</span>
          <button className="btn-sm" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>
            Next →
          </button>
        </div>
      )}

      <style>{`
        .audit-page { padding:24px; max-width:1400px; margin:0 auto; }
        .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
        .page-header h1 { margin:0 0 4px; font-size:22px; }
        .page-subtitle { margin:0; color:#888; font-size:13px; }
        .btn-integrity { padding:8px 16px; border-radius:5px; border:1px solid #333; background:#1e2130; color:#ccc; cursor:pointer; font-size:13px; }
        .btn-integrity.ok   { border-color:#2ecc71; color:#2ecc71; background:#0d2d1a; }
        .btn-integrity.fail { border-color:#e74c3c; color:#e74c3c; background:#2d0d0d; }
        .integrity-banner { padding:10px 16px; border-radius:6px; font-size:13px; margin-bottom:16px; }
        .integrity-banner.ok   { background:#0d2d1a; border:1px solid #1a5a2a; color:#2ecc71; }
        .integrity-banner.fail { background:#2d0d0d; border:1px solid #5a1a1a; color:#e74c3c; }
        .filter-bar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
        .filter-input { background:#1a1f2e; border:1px solid #2a2f3e; border-radius:5px; color:#ccc; padding:7px 10px; font-size:13px; flex:1; min-width:120px; }
        .result-count { font-size:12px; color:#666; margin-bottom:8px; }
        .log-table-wrap { overflow-x:auto; border-radius:8px; border:1px solid #2a2f3e; }
        .log-table { width:100%; border-collapse:collapse; font-size:12px; }
        .log-table th { text-align:left; padding:8px 10px; background:#161b28; border-bottom:1px solid #2a2f3e; color:#668; font-weight:500; white-space:nowrap; }
        .log-table td { padding:7px 10px; border-bottom:1px solid #1a1f2e; vertical-align:middle; }
        .log-table tr:hover td { background:rgba(255,255,255,.02); }
        .row-fail td { background:rgba(231,76,60,.04); }
        .mono { font-family:monospace; color:#9aa; }
        .truncate { max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .desc { color:#888; }
        .pagination { display:flex; justify-content:center; align-items:center; gap:16px; margin-top:16px; font-size:13px; color:#888; }
        .btn-sm { background:#2a3a4a; color:#4a9eff; border:none; border-radius:4px; padding:6px 14px; cursor:pointer; font-size:13px; }
        .btn-sm:disabled { opacity:.4; cursor:default; }
        .btn-secondary { background:#333; color:#ccc; border:none; border-radius:5px; padding:7px 14px; cursor:pointer; font-size:13px; }
        .page-loading, .page-error { display:flex; align-items:center; justify-content:center; height:50vh; font-size:16px; color:#888; }
      `}</style>
    </div>
  );
}
