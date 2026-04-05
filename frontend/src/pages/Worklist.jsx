// src/pages/Worklist.jsx
// Main radiology worklist — replaces your existing Worklist.jsx
// Adds: partition filter, OHIF launch, real-time polling, burn shortcut

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import FilterBar  from "../components/FilterBar";
import StudyTable from "../components/StudyTable";
import { useStudies } from "../hooks/useStudies";
import api from "../lib/api";

export default function Worklist() {
  const navigate = useNavigate();
  const [partitions, setPartitions] = useState([]);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const {
    studies, total, loading, error,
    page, setPage, pageSize,
    filters, updateFilter, resetFilters,
    sortBy, sortDir, toggleSort,
    refresh,
  } = useStudies();

  // Load partitions for filter dropdown
  useEffect(() => {
    api.get("/api/partitions").then(r => setPartitions(r.data || [])).catch(() => {});
  }, []);

  // Auto-refresh every 30s if toggled
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(refresh, 30_000);
    return () => clearInterval(id);
  }, [autoRefresh, refresh]);

  const handleDelete = async (study) => {
    if (!confirm(`Delete study for ${study.patient?.patient_name}?\nThis cannot be undone.`)) return;
    try {
      await api.delete(`/api/studies/${study.id}`);
      refresh();
    } catch (e) {
      alert(e.response?.data?.detail || "Delete failed");
    }
  };

  const handleBurn = (study) => {
    navigate(`/burn?studyId=${study.id}`);
  };

  return (
    <div className="worklist-page">
      <div className="worklist-header">
        <div className="header-left">
          <h1>Worklist</h1>
          <span className="study-count">{total} studies</span>
        </div>
        <div className="header-right">
          <label className="auto-refresh-toggle">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={e => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh
          </label>
          <button className="btn-icon" onClick={refresh} title="Refresh" disabled={loading}>
            {loading ? "…" : "↻"}
          </button>
          <button className="btn-primary" onClick={() => navigate("/upload")}>
            + Upload DICOM
          </button>
        </div>
      </div>

      <FilterBar
        filters={filters}
        onUpdate={updateFilter}
        onReset={resetFilters}
        partitions={partitions}
      />

      <StudyTable
        studies={studies}
        total={total}
        loading={loading}
        error={error}
        page={page}
        setPage={setPage}
        pageSize={pageSize}
        sortBy={sortBy}
        sortDir={sortDir}
        onSort={toggleSort}
        onBurn={handleBurn}
        onDelete={handleDelete}
        showPartition={partitions.length > 1}
      />

      <style>{`
        .worklist-page { display:flex; flex-direction:column; height:100vh; overflow:hidden; }
        .worklist-header { display:flex; justify-content:space-between; align-items:center; padding:12px 20px; border-bottom:1px solid #2a2f3e; flex-shrink:0; }
        .header-left { display:flex; align-items:baseline; gap:12px; }
        .worklist-header h1 { margin:0; font-size:20px; font-weight:600; }
        .study-count { font-size:13px; color:#666; }
        .header-right { display:flex; align-items:center; gap:10px; }
        .auto-refresh-toggle { display:flex; align-items:center; gap:6px; font-size:12px; color:#888; cursor:pointer; user-select:none; }
        .btn-icon { background:#1e2330; border:1px solid #2a2f3e; color:#ccc; width:32px; height:32px; border-radius:5px; font-size:16px; cursor:pointer; transition:background .15s; }
        .btn-icon:hover { background:#2a3a5a; }
        .btn-primary { background:#4a9eff; color:#fff; border:none; border-radius:5px; padding:7px 14px; font-size:13px; cursor:pointer; font-weight:500; }
        .btn-primary:hover { background:#3a8eef; }
      `}</style>
    </div>
  );
}
