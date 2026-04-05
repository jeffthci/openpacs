// src/pages/Analytics.jsx
// ─────────────────────────────────────────────────────────────────
// Analytics dashboard: study volumes, modality breakdown,
// storage trend, hourly heatmap, top referring physicians.
// Uses Recharts for all visualizations.

import { useState, useEffect } from "react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import api from "../lib/api";

const MODALITY_COLORS = [
  "#4a9eff","#9b59b6","#2ecc71","#e67e22","#e74c3c",
  "#1abc9c","#f39c12","#16a085","#8e44ad","#3498db",
];

function Card({ title, children, span = 1 }) {
  return (
    <div className="analytics-card" style={{ gridColumn: `span ${span}` }}>
      <div className="analytics-card-title">{title}</div>
      {children}
    </div>
  );
}

function StatNumber({ value, label, delta }) {
  return (
    <div className="stat-number">
      <div className="stat-n-value">{value?.toLocaleString()}</div>
      <div className="stat-n-label">{label}</div>
      {delta != null && (
        <div className={`stat-delta ${delta >= 0 ? "up" : "down"}`}>
          {delta >= 0 ? "▲" : "▼"} {Math.abs(delta)}%
        </div>
      )}
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <div className="tooltip-label">{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color }}>
          {p.name}: <strong>{p.value?.toLocaleString?.() ?? p.value}</strong>
        </div>
      ))}
    </div>
  );
};

export default function Analytics() {
  const [overview,   setOverview]   = useState(null);
  const [daily,      setDaily]      = useState([]);
  const [modality,   setModality]   = useState([]);
  const [hourly,     setHourly]     = useState([]);
  const [referring,  setReferring]  = useState([]);
  const [storage,    setStorage]    = useState([]);
  const [days,       setDays]       = useState(30);
  const [loading,    setLoading]    = useState(true);

  const fetchAll = async (d = days) => {
    setLoading(true);
    try {
      const [ov, da, mo, ho, re, st] = await Promise.all([
        api.get("/stats/overview"),
        api.get(`/stats/daily?days=${d}`),
        api.get(`/stats/modality?days=${d}`),
        api.get(`/stats/hourly?days=${d}`),
        api.get(`/stats/top-referring?days=${d}&limit=8`),
        api.get(`/stats/storage-trend?days=${d}`),
      ]);
      setOverview(ov.data);
      setDaily(da.data);
      setModality(mo.data);
      setHourly(ho.data);
      setReferring(re.data);
      setStorage(st.data);
    } catch (e) {
      console.error("Analytics fetch error", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const changeDays = d => { setDays(d); fetchAll(d); };

  // Format date labels for x-axis
  const fmtDate = d => d ? `${d.slice(4, 6)}/${d.slice(6, 8)}` : "";
  const fmtHour = h => `${String(h).padStart(2, "0")}:00`;

  return (
    <div className="analytics-page">
      <div className="analytics-header">
        <h1>Analytics</h1>
        <div className="day-picker">
          {[7, 14, 30, 90, 365].map(d => (
            <button
              key={d}
              className={`day-btn ${days === d ? "active" : ""}`}
              onClick={() => changeDays(d)}
            >
              {d === 365 ? "1yr" : `${d}d`}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="analytics-loading">Loading analytics…</div>}

      {overview && (
        <div className="analytics-grid">

          {/* ── Overview numbers ─────────────────────────────── */}
          <Card title="Server Overview" span={4}>
            <div className="overview-numbers">
              <StatNumber value={overview.patients}          label="Total Patients" />
              <StatNumber value={overview.studies}           label="Total Studies" />
              <StatNumber value={overview.instances}         label="Total Instances" />
              <StatNumber value={overview.studies_today}     label="Studies Today" />
              <StatNumber value={overview.studies_this_week} label="This Week" />
              <StatNumber value={overview.storage_gb + " GB"} label="Storage Used" />
            </div>
          </Card>

          {/* ── Daily volume bar chart ────────────────────────── */}
          <Card title={`Studies per Day — Last ${days} Days`} span={3}>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={daily} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3e" />
                <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fill: "#668", fontSize: 11 }} interval="preserveStartEnd" />
                <YAxis tick={{ fill: "#668", fontSize: 11 }} allowDecimals={false} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" fill="#4a9eff" radius={[3, 3, 0, 0]} name="Studies" />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          {/* ── Modality pie chart ────────────────────────────── */}
          <Card title="Modality Distribution">
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={modality} dataKey="count" nameKey="modality"
                  cx="50%" cy="50%" outerRadius={80} innerRadius={40}
                  paddingAngle={2}
                >
                  {modality.map((entry, i) => (
                    <Cell key={entry.modality} fill={entry.color || MODALITY_COLORS[i % MODALITY_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(val, name) => [val.toLocaleString(), name]} />
                <Legend
                  formatter={(val) => <span style={{ fontSize: 11, color: "#ccc" }}>{val}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          </Card>

          {/* ── Storage trend line chart ──────────────────────── */}
          <Card title="Cumulative Storage (GB)" span={2}>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={storage} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3e" />
                <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fill: "#668", fontSize: 11 }} interval="preserveStartEnd" />
                <YAxis tick={{ fill: "#668", fontSize: 11 }} unit=" GB" />
                <Tooltip content={<CustomTooltip />} />
                <Line type="monotone" dataKey="gb" stroke="#2ecc71" strokeWidth={2} dot={false} name="GB" />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          {/* ── Hourly bar chart ──────────────────────────────── */}
          <Card title="Studies by Hour of Day" span={2}>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={hourly} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3e" />
                <XAxis dataKey="hour" tickFormatter={fmtHour} tick={{ fill: "#668", fontSize: 10 }} interval={3} />
                <YAxis tick={{ fill: "#668", fontSize: 11 }} allowDecimals={false} />
                <Tooltip content={<CustomTooltip />} formatter={(v) => [v, "Studies"]} labelFormatter={fmtHour} />
                <Bar dataKey="count" fill="#9b59b6" radius={[2, 2, 0, 0]} name="Studies" />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          {/* ── Top referring physicians ──────────────────────── */}
          <Card title="Top Referring Physicians" span={2}>
            <div className="referring-list">
              {referring.map((r, i) => (
                <div key={i} className="referring-row">
                  <div className="referring-rank">#{i + 1}</div>
                  <div className="referring-name">{r.physician || "Unknown"}</div>
                  <div className="referring-bar-wrap">
                    <div
                      className="referring-bar"
                      style={{ width: `${Math.round((r.count / (referring[0]?.count || 1)) * 100)}%` }}
                    />
                  </div>
                  <div className="referring-count">{r.count}</div>
                </div>
              ))}
              {referring.length === 0 && (
                <div style={{ color: "#666", fontSize: 12, padding: "16px 0" }}>
                  No referring physician data
                </div>
              )}
            </div>
          </Card>

          {/* ── Modality table ────────────────────────────────── */}
          <Card title="Modality Summary Table" span={2}>
            <table className="modality-table">
              <thead>
                <tr><th>Modality</th><th>Studies</th><th>Share</th></tr>
              </thead>
              <tbody>
                {modality.map(m => {
                  const total = modality.reduce((s, x) => s + x.count, 0);
                  return (
                    <tr key={m.modality}>
                      <td>
                        <span style={{
                          display: "inline-block", width: 8, height: 8,
                          borderRadius: 2, background: m.color, marginRight: 6,
                        }} />
                        {m.modality}
                      </td>
                      <td>{m.count.toLocaleString()}</td>
                      <td style={{ color: "#888" }}>
                        {total > 0 ? Math.round((m.count / total) * 100) : 0}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>

        </div>
      )}

      <style>{`
        .analytics-page { padding: 24px; max-width: 1400px; margin: 0 auto; }
        .analytics-header { display:flex; justify-content:space-between; align-items:center; margin-bottom: 24px; }
        .analytics-header h1 { margin:0; font-size:24px; }
        .day-picker { display:flex; gap:4px; }
        .day-btn { background:#1e2436; border:1px solid #2a2f3e; color:#888; border-radius:5px; padding:5px 12px; cursor:pointer; font-size:13px; }
        .day-btn.active { background:#1a3a5c; border-color:#4a9eff; color:#4a9eff; }
        .analytics-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; }
        .analytics-card { background:#1e2436; border-radius:8px; padding:16px; border:1px solid #2a2f3e; }
        .analytics-card-title { font-size:13px; font-weight:500; color:#888; margin-bottom:14px; text-transform:uppercase; letter-spacing:.5px; }
        .overview-numbers { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
        .stat-number { text-align:center; }
        .stat-n-value { font-size:24px; font-weight:600; color:#fff; }
        .stat-n-label { font-size:11px; color:#668; margin-top:2px; text-transform:uppercase; }
        .stat-delta { font-size:11px; margin-top:3px; }
        .stat-delta.up { color:#2ecc71; }
        .stat-delta.down { color:#e74c3c; }
        .chart-tooltip { background:#1e2436; border:1px solid #2a2f3e; border-radius:6px; padding:8px 12px; font-size:12px; }
        .tooltip-label { color:#888; margin-bottom:4px; font-size:11px; }
        .referring-list { display:flex; flex-direction:column; gap:6px; }
        .referring-row { display:grid; grid-template-columns:28px 1fr 80px 40px; align-items:center; gap:8px; }
        .referring-rank { font-size:11px; color:#666; }
        .referring-name { font-size:12px; color:#ccc; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .referring-bar-wrap { height:6px; background:#2a2f3e; border-radius:3px; overflow:hidden; }
        .referring-bar { height:100%; background:#4a9eff; border-radius:3px; }
        .referring-count { font-size:12px; color:#888; text-align:right; }
        .modality-table { width:100%; border-collapse:collapse; font-size:13px; }
        .modality-table th { text-align:left; padding:6px 8px; border-bottom:1px solid #2a2f3e; color:#668; font-weight:500; }
        .modality-table td { padding:5px 8px; border-bottom:1px solid #1a1f2e; }
        .analytics-loading { display:flex; align-items:center; justify-content:center; height:40vh; color:#668; }
        @media (max-width:900px) { .analytics-grid { grid-template-columns:1fr 1fr; } }
        @media (max-width:600px) { .analytics-grid { grid-template-columns:1fr; } }
      `}</style>
    </div>
  );
}
