// src/components/StudyTable.jsx
// Reusable study list table with sortable columns, row actions, pagination.

import { useNavigate } from "react-router-dom";

const MODALITY_COLORS = {
  CT:  "#4a9eff", MR: "#a78bfa", CR: "#34d399",
  DX:  "#34d399", US: "#fbbf24", NM: "#f87171",
  PT:  "#fb923c", MG: "#e879f9", XA: "#38bdf8",
  RF:  "#a3e635", SC: "#94a3b8",
};

function ModalityBadge({ mod }) {
  const color = MODALITY_COLORS[mod] || "#888";
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 10,
      fontSize: 11, fontWeight: 600, letterSpacing: ".5px",
      background: color + "22", color, border: `1px solid ${color}44`,
    }}>
      {mod}
    </span>
  );
}

function SortHeader({ label, col, sortBy, sortDir, onSort }) {
  const active = sortBy === col;
  return (
    <th onClick={() => onSort(col)} style={{ cursor: "pointer", userSelect: "none",
      color: active ? "#fff" : "#888", whiteSpace: "nowrap" }}>
      {label}
      {active && <span style={{ marginLeft: 4, fontSize: 10 }}>
        {sortDir === "asc" ? "▲" : "▼"}
      </span>}
    </th>
  );
}

export default function StudyTable({
  studies, total, loading, error,
  page, setPage, pageSize,
  sortBy, sortDir, onSort,
  onOpen, onBurn, onDelete,
  showPartition = false,
}) {
  const navigate   = useNavigate();
  const totalPages = Math.ceil(total / pageSize);

  const openStudy = (s) => {
    if (onOpen) onOpen(s);
    else navigate(`/study/${s.id}`);
  };

  if (error) return <div className="table-error">{error}</div>;

  return (
    <div className="study-table-wrap">
      <div className="table-scroll">
        <table className="study-table">
          <thead>
            <tr>
              <SortHeader label="Patient"      col="patient_name" {...{sortBy, sortDir, onSort}} />
              <SortHeader label="ID"           col="patient_id"   {...{sortBy, sortDir, onSort}} />
              <SortHeader label="Date"         col="study_date"   {...{sortBy, sortDir, onSort}} />
              <SortHeader label="Description"  col="study_description" {...{sortBy, sortDir, onSort}} />
              <th>Modality</th>
              <SortHeader label="Accession"    col="accession_number" {...{sortBy, sortDir, onSort}} />
              <SortHeader label="Images"       col="instances"    {...{sortBy, sortDir, onSort}} />
              {showPartition && <th>Partition</th>}
              <th style={{ width: 140 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={showPartition ? 9 : 8} className="table-loading">
                Loading…
              </td></tr>
            )}
            {!loading && studies.length === 0 && (
              <tr><td colSpan={showPartition ? 9 : 8} className="table-empty">
                No studies found
              </td></tr>
            )}
            {!loading && studies.map((s) => (
              <tr key={s.id} className="study-row" onDoubleClick={() => openStudy(s)}>
                <td className="patient-name">{s.patient?.patient_name || s.patient_name || "—"}</td>
                <td className="mono">{s.patient?.patient_id || s.patient_id || "—"}</td>
                <td className="mono">{formatDate(s.study_date)}</td>
                <td className="description">{s.study_description || "—"}</td>
                <td>
                  {(s.modalities_in_study || [s.modality]).filter(Boolean).map(m => (
                    <ModalityBadge key={m} mod={m} />
                  ))}
                </td>
                <td className="mono small">{s.accession_number || "—"}</td>
                <td className="center">{s.number_of_study_related_instances ?? "—"}</td>
                {showPartition && (
                  <td><span className="partition-tag">{s.partition?.ae_title || "—"}</span></td>
                )}
                <td>
                  <div className="row-actions">
                    <button
                      className="act-btn view"
                      title="Open Study"
                      onClick={() => openStudy(s)}
                    >View</button>
                    <button
                      className="act-btn ohif"
                      title="Open in OHIF"
                      onClick={() => navigate(`/ohif?studyUID=${s.study_instance_uid}`)}
                    >OHIF</button>
                    {onBurn && (
                      <button
                        className="act-btn burn"
                        title="Burn to CD/ISO"
                        onClick={() => onBurn(s)}
                      >Burn</button>
                    )}
                    {onDelete && (
                      <button
                        className="act-btn del"
                        title="Delete Study"
                        onClick={() => onDelete(s)}
                      >✕</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="table-footer">
        <span className="table-count">
          {total} {total === 1 ? "study" : "studies"}
          {total > pageSize && ` (page ${page} of ${totalPages})`}
        </span>
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage(1)}>«</button>
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>‹</button>
          {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
            const p = Math.max(1, Math.min(page - 2, totalPages - 4)) + i;
            return (
              <button
                key={p}
                className={p === page ? "active" : ""}
                onClick={() => setPage(p)}
              >{p}</button>
            );
          })}
          <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>›</button>
          <button disabled={page >= totalPages} onClick={() => setPage(totalPages)}>»</button>
        </div>
      </div>

      <style>{`
        .study-table-wrap { display:flex; flex-direction:column; flex:1; overflow:hidden; }
        .table-scroll { overflow-x:auto; overflow-y:auto; flex:1; }
        .study-table { width:100%; border-collapse:collapse; font-size:13px; }
        .study-table th { padding:10px 12px; border-bottom:2px solid #2a2f3e; text-align:left; font-size:11px; font-weight:500; letter-spacing:.5px; text-transform:uppercase; position:sticky; top:0; background:#141820; z-index:1; }
        .study-table td { padding:9px 12px; border-bottom:1px solid #1e2330; vertical-align:middle; }
        .study-row:hover td { background:#1a2035; cursor:pointer; }
        .table-loading, .table-empty, .table-error { text-align:center; padding:40px; color:#666; font-size:14px; }
        .table-error { color:#e74c3c; }
        .patient-name { font-weight:500; color:#e0e4f0; max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .description { color:#aab; max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .mono { font-family:monospace; font-size:12px; color:#8899aa; }
        .small { font-size:11px; }
        .center { text-align:center; }
        .partition-tag { background:#1a2540; color:#4a9eff; padding:2px 8px; border-radius:10px; font-size:11px; }
        .row-actions { display:flex; gap:4px; }
        .act-btn { padding:3px 8px; border:none; border-radius:4px; font-size:11px; cursor:pointer; font-weight:500; transition:opacity .15s; }
        .act-btn:hover { opacity:.85; }
        .act-btn.view { background:#1a3a5c; color:#4a9eff; }
        .act-btn.ohif { background:#2a1a5c; color:#a78bfa; }
        .act-btn.burn { background:#3a2a1a; color:#f59e0b; }
        .act-btn.del  { background:#3a1a1a; color:#e74c3c; }
        .table-footer { display:flex; justify-content:space-between; align-items:center; padding:10px 16px; border-top:1px solid #2a2f3e; flex-shrink:0; }
        .table-count { font-size:12px; color:#666; }
        .pagination { display:flex; gap:4px; }
        .pagination button { background:#1e2330; border:1px solid #2a2f3e; color:#ccc; width:28px; height:28px; border-radius:4px; cursor:pointer; font-size:12px; transition:background .15s; }
        .pagination button:hover:not(:disabled) { background:#2a3a5a; }
        .pagination button.active { background:#4a9eff; color:#fff; border-color:#4a9eff; }
        .pagination button:disabled { opacity:.3; cursor:default; }
      `}</style>
    </div>
  );
}

function formatDate(d) {
  if (!d) return "—";
  if (d.length === 8) return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`;
  return d.slice(0, 10);
}
