// src/pages/Patients.jsx
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";

export default function Patients() {
  const navigate              = useNavigate();
  const [patients, setPatients] = useState([]);
  const [total,    setTotal]    = useState(0);
  const [loading,  setLoading]  = useState(false);
  const [search,   setSearch]   = useState("");
  const [page,     setPage]     = useState(1);
  const PAGE_SIZE               = 50;

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/patients", {
        params: { search, skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE },
      });
      if (Array.isArray(data)) { setPatients(data); setTotal(data.length); }
      else { setPatients(data.items || []); setTotal(data.total || 0); }
    } catch { setPatients([]); }
    finally { setLoading(false); }
  }, [search, page]);

  useEffect(() => { fetch(); }, [fetch]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="patients-page">
      <div className="page-hdr">
        <h1>Patients</h1>
        <span className="count">{total} patients</span>
      </div>

      <div className="search-row">
        <input
          className="search-input"
          placeholder="Search by name or patient ID…"
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1); }}
        />
      </div>

      <table className="ptable">
        <thead>
          <tr>
            <th>Patient Name</th>
            <th>Patient ID</th>
            <th>Date of Birth</th>
            <th>Sex</th>
            <th>Studies</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {loading && <tr><td colSpan={6} className="center muted">Loading…</td></tr>}
          {!loading && patients.length === 0 && (
            <tr><td colSpan={6} className="center muted">No patients found</td></tr>
          )}
          {!loading && patients.map(p => (
            <tr key={p.id} className="prow" onClick={() => navigate(`/?patient_id=${p.patient_id}`)}>
              <td className="name">{p.patient_name || "—"}</td>
              <td className="mono">{p.patient_id}</td>
              <td className="mono">{fmtDob(p.date_of_birth)}</td>
              <td>{p.sex || "—"}</td>
              <td className="center">{p.study_count ?? "—"}</td>
              <td>
                <button className="btn-link" onClick={e => { e.stopPropagation(); navigate(`/?patient_id=${p.patient_id}`); }}>
                  View Studies →
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage(p => p-1)}>‹ Prev</button>
          <span>{page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(p => p+1)}>Next ›</button>
        </div>
      )}

      <style>{`
        .patients-page { padding: 24px; }
        .page-hdr { display: flex; align-items: baseline; gap: 12px; margin-bottom: 20px; }
        .page-hdr h1 { margin: 0; font-size: 22px; }
        .count { color: #666; font-size: 13px; }
        .search-row { margin-bottom: 16px; }
        .search-input { background: #1e2330; border: 1px solid #2a2f3e; border-radius: 6px; color: #ddd; padding: 9px 14px; font-size: 13px; width: 360px; outline: none; }
        .search-input:focus { border-color: #4a9eff; }
        .ptable { width: 100%; border-collapse: collapse; font-size: 13px; }
        .ptable th { text-align: left; padding: 9px 12px; border-bottom: 2px solid #2a2f3e; font-size: 11px; color: #888; font-weight: 500; text-transform: uppercase; letter-spacing: .4px; }
        .ptable td { padding: 10px 12px; border-bottom: 1px solid #1e2330; }
        .prow { cursor: pointer; }
        .prow:hover td { background: #1a2035; }
        .name { font-weight: 500; color: #e0e4f0; }
        .mono { font-family: monospace; font-size: 12px; color: #8899aa; }
        .center { text-align: center; }
        .muted { color: #666; text-align: center; padding: 32px; }
        .btn-link { background: none; border: none; color: #4a9eff; font-size: 12px; cursor: pointer; }
        .btn-link:hover { text-decoration: underline; }
        .pagination { display: flex; align-items: center; gap: 12px; justify-content: center; margin-top: 20px; font-size: 13px; color: #888; }
        .pagination button { background: #1e2330; border: 1px solid #2a2f3e; color: #ccc; padding: 6px 14px; border-radius: 5px; cursor: pointer; }
        .pagination button:disabled { opacity: .3; cursor: default; }
      `}</style>
    </div>
  );
}

function fmtDob(d) {
  if (!d || d.length !== 8) return "—";
  return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`;
}
