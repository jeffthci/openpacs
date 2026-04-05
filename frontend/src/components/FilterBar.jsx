// src/components/FilterBar.jsx
// Collapsible filter bar used by Worklist and other study list pages.

import { useState } from "react";

const MODALITIES = ["", "CT", "MR", "CR", "DX", "US", "NM", "PT", "MG", "XA", "RF", "SC", "OT"];

export default function FilterBar({ filters, onUpdate, onReset, partitions = [] }) {
  const [expanded, setExpanded] = useState(false);
  const hasActive = Object.values(filters).some(v => v !== "");

  return (
    <div className="filter-bar">
      <div className="filter-row-main">
        <input
          className="filter-input wide"
          placeholder="Patient name…"
          value={filters.patient_name}
          onChange={e => onUpdate("patient_name", e.target.value)}
        />
        <input
          className="filter-input"
          placeholder="Patient ID…"
          value={filters.patient_id}
          onChange={e => onUpdate("patient_id", e.target.value)}
        />
        <input
          className="filter-input"
          placeholder="Accession…"
          value={filters.accession}
          onChange={e => onUpdate("accession", e.target.value)}
        />
        <select
          className="filter-select"
          value={filters.modality}
          onChange={e => onUpdate("modality", e.target.value)}
        >
          {MODALITIES.map(m => (
            <option key={m} value={m}>{m || "Any modality"}</option>
          ))}
        </select>
        <button
          className={`filter-toggle ${expanded ? "active" : ""}`}
          onClick={() => setExpanded(e => !e)}
          title="More filters"
        >
          ⚙ {expanded ? "Less" : "More"}
        </button>
        {hasActive && (
          <button className="filter-clear" onClick={onReset} title="Clear all filters">
            × Clear
          </button>
        )}
      </div>

      {expanded && (
        <div className="filter-row-extra">
          <div className="filter-group">
            <label>Date from</label>
            <input
              type="date"
              className="filter-input"
              value={filters.date_from}
              onChange={e => onUpdate("date_from", e.target.value)}
            />
          </div>
          <div className="filter-group">
            <label>Date to</label>
            <input
              type="date"
              className="filter-input"
              value={filters.date_to}
              onChange={e => onUpdate("date_to", e.target.value)}
            />
          </div>
          {partitions.length > 0 && (
            <div className="filter-group">
              <label>Partition</label>
              <select
                className="filter-select"
                value={filters.partition}
                onChange={e => onUpdate("partition", e.target.value)}
              >
                <option value="">All partitions</option>
                {partitions.map(p => (
                  <option key={p.id} value={p.ae_title}>{p.ae_title} — {p.description}</option>
                ))}
              </select>
            </div>
          )}
          <div className="filter-group">
            <label>Status</label>
            <select
              className="filter-select"
              value={filters.status || ""}
              onChange={e => onUpdate("status", e.target.value)}
            >
              <option value="">Any</option>
              <option value="received">Received</option>
              <option value="reported">Reported</option>
              <option value="pending">Pending report</option>
            </select>
          </div>
        </div>
      )}

      <style>{`
        .filter-bar { padding:12px 16px; border-bottom:1px solid #2a2f3e; background:#141820; }
        .filter-row-main { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
        .filter-row-extra { display:flex; gap:16px; flex-wrap:wrap; margin-top:10px; padding-top:10px; border-top:1px solid #2a2f3e; }
        .filter-group { display:flex; flex-direction:column; gap:4px; }
        .filter-group label { font-size:11px; color:#666; text-transform:uppercase; letter-spacing:.4px; }
        .filter-input { background:#1e2330; border:1px solid #2a2f3e; border-radius:5px; color:#ddd; padding:7px 10px; font-size:13px; outline:none; transition:border-color .2s; }
        .filter-input:focus { border-color:#4a9eff; }
        .filter-input.wide { flex:1; min-width:180px; }
        .filter-select { background:#1e2330; border:1px solid #2a2f3e; border-radius:5px; color:#ddd; padding:7px 10px; font-size:13px; outline:none; cursor:pointer; }
        .filter-toggle { background:#1e2330; border:1px solid #2a2f3e; border-radius:5px; color:#888; padding:7px 12px; font-size:12px; cursor:pointer; white-space:nowrap; transition:all .2s; }
        .filter-toggle.active { border-color:#4a9eff; color:#4a9eff; background:#1a2d4a; }
        .filter-clear { background:none; border:none; color:#e74c3c; font-size:12px; cursor:pointer; padding:7px 10px; white-space:nowrap; }
        .filter-clear:hover { text-decoration:underline; }
      `}</style>
    </div>
  );
}
