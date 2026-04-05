// src/components/DICOMTagBrowser.jsx
// ─────────────────────────────────────────────────────────────────
// Full DICOM tag tree viewer for any instance.
// Fetches metadata via WADO-RS /instances/{uid}/metadata
// and renders all tags in a searchable, collapsible tree.

import { useState, useEffect, useMemo } from "react";
import api from "../lib/api";

const VR_COLORS = {
  UI: "#4a9eff", DA: "#2ecc71", TM: "#27ae60", DT: "#1abc9c",
  PN: "#9b59b6", LO: "#8e44ad", SH: "#6c3483",
  US: "#e67e22", SS: "#d35400", UL: "#ca6f1e",
  DS: "#f39c12", IS: "#d68910", FL: "#f0b27a",
  CS: "#e74c3c", AT: "#c0392b",
  OB: "#7f8c8d", OW: "#626567", UN: "#717d7e",
  SQ: "#2980b9",
};

// Common tag names for display
const KNOWN_TAGS = {
  "00080016": "SOP Class UID",       "00080018": "SOP Instance UID",
  "00080020": "Study Date",          "00080021": "Series Date",
  "00080030": "Study Time",          "00080060": "Modality",
  "00080070": "Manufacturer",        "00080080": "Institution Name",
  "00100010": "Patient Name",        "00100020": "Patient ID",
  "00100030": "Patient Birth Date",  "00100040": "Patient Sex",
  "0020000D": "Study Instance UID",  "0020000E": "Series Instance UID",
  "00200011": "Series Number",       "00200013": "Instance Number",
  "00280010": "Rows",                "00280011": "Columns",
  "00280030": "Pixel Spacing",       "00280100": "Bits Allocated",
  "00280101": "Bits Stored",         "00281050": "Window Center",
  "00281051": "Window Width",        "7FE00010": "Pixel Data",
};

function TagRow({ tagKey, tagData, depth = 0 }) {
  const [expanded, setExpanded] = useState(false);
  const isSeq = tagData?.vr === "SQ";
  const isBulk = tagData?.vr === "OB" || tagData?.vr === "OW";
  const label  = KNOWN_TAGS[tagKey] || "";
  const vr     = tagData?.vr || "??";
  const values = tagData?.Value || [];

  const displayValue = isBulk
    ? `[Binary data — ${vr}]`
    : isSeq
      ? `[${values.length} item${values.length !== 1 ? "s" : ""}]`
      : values.map(v => {
          if (typeof v === "object" && v !== null) {
            if ("Alphabetic" in v) return v.Alphabetic;
            return JSON.stringify(v);
          }
          return String(v);
        }).join(" \\ ");

  return (
    <>
      <tr
        className={`tag-row depth-${Math.min(depth, 3)} ${isSeq ? "seq-row" : ""}`}
        onClick={isSeq ? () => setExpanded(e => !e) : undefined}
        style={{ cursor: isSeq ? "pointer" : "default" }}
      >
        <td className="tag-key">
          {"  ".repeat(depth)}
          {isSeq && <span className="expand-arrow">{expanded ? "▼" : "▶"} </span>}
          {tagKey.slice(0, 4)},{tagKey.slice(4)}
        </td>
        <td>
          <span className="vr-badge" style={{ background: VR_COLORS[vr] + "33", color: VR_COLORS[vr] || "#888" }}>
            {vr}
          </span>
        </td>
        <td className="tag-name">{label}</td>
        <td className="tag-value" title={typeof displayValue === "string" ? displayValue : ""}>
          {displayValue}
        </td>
      </tr>
      {isSeq && expanded && values.map((seqItem, i) => (
        <SeqItem key={i} index={i} item={seqItem} depth={depth + 1} />
      ))}
    </>
  );
}

function SeqItem({ index, item, depth }) {
  return (
    <>
      <tr className={`seq-item-header depth-${Math.min(depth, 3)}`}>
        <td colSpan={4} className="seq-item-label">
          {"  ".repeat(depth)}Item {index + 1}
        </td>
      </tr>
      {Object.entries(item || {}).map(([k, v]) => (
        <TagRow key={k} tagKey={k} tagData={v} depth={depth + 1} />
      ))}
    </>
  );
}

export default function DICOMTagBrowser({ studyUID, seriesUID, instanceUID, onClose }) {
  const [metadata, setMetadata] = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);
  const [search,   setSearch]   = useState("");

  useEffect(() => {
    if (!instanceUID) return;
    setLoading(true);
    api.get(`/wado/studies/${studyUID}/series/${seriesUID}/instances/${instanceUID}/metadata`)
      .then(r => {
        setMetadata(r.data?.[0] || {});
        setLoading(false);
      })
      .catch(e => {
        setError(e.message);
        setLoading(false);
      });
  }, [studyUID, seriesUID, instanceUID]);

  const filtered = useMemo(() => {
    if (!metadata) return [];
    const s = search.toLowerCase();
    return Object.entries(metadata).filter(([k, v]) => {
      if (!s) return true;
      const label = (KNOWN_TAGS[k] || "").toLowerCase();
      const val   = JSON.stringify(v?.Value || "").toLowerCase();
      return k.toLowerCase().includes(s) || label.includes(s) || val.includes(s);
    });
  }, [metadata, search]);

  return (
    <div className="tag-browser-overlay" onClick={onClose}>
      <div className="tag-browser" onClick={e => e.stopPropagation()}>
        <div className="tag-browser-header">
          <span>DICOM Tag Browser</span>
          <div className="tag-search-wrap">
            <input
              className="tag-search"
              placeholder="Search tags, names, values…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              autoFocus
            />
          </div>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        {loading && <div className="tag-loading">Loading metadata…</div>}
        {error   && <div className="tag-error">Error: {error}</div>}

        {metadata && (
          <div className="tag-table-wrap">
            <table className="tag-table">
              <thead>
                <tr>
                  <th>Tag</th><th>VR</th><th>Name</th><th>Value</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(([k, v]) => (
                  <TagRow key={k} tagKey={k} tagData={v} depth={0} />
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan={4} style={{ color: "#666", textAlign: "center", padding: 20 }}>
                    No tags match "{search}"
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        <style>{`
          .tag-browser-overlay {
            position: fixed; inset: 0; background: rgba(0,0,0,.75);
            display: flex; align-items: center; justify-content: center; z-index: 9000;
          }
          .tag-browser {
            background: #141820; border-radius: 10px;
            width: 900px; max-width: 96vw; height: 80vh;
            display: flex; flex-direction: column; overflow: hidden;
            border: 1px solid #2a2f3e;
          }
          .tag-browser-header {
            display: flex; align-items: center; gap: 12px;
            padding: 12px 16px; border-bottom: 1px solid #2a2f3e;
            font-weight: 500; font-size: 14px; background: #1a1f2e;
          }
          .tag-search-wrap { flex: 1; }
          .tag-search {
            width: 100%; background: #0e1118; border: 1px solid #333;
            border-radius: 5px; color: #ccc; padding: 6px 10px; font-size: 13px;
          }
          .close-btn {
            background: none; border: none; color: #888;
            cursor: pointer; font-size: 16px; padding: 0 4px;
          }
          .tag-table-wrap { flex: 1; overflow-y: auto; }
          .tag-table { width: 100%; border-collapse: collapse; font-size: 12px; }
          .tag-table th {
            position: sticky; top: 0; background: #1a1f2e;
            text-align: left; padding: 7px 10px;
            border-bottom: 1px solid #2a2f3e; color: #668; font-weight: 500;
          }
          .tag-row td { padding: 4px 10px; border-bottom: 1px solid #1a1f2e; }
          .tag-row:hover td { background: rgba(255,255,255,.03); }
          .tag-row.seq-row:hover td { background: rgba(41,128,185,.1); cursor: pointer; }
          .depth-1 td { background: rgba(255,255,255,.01); }
          .depth-2 td { background: rgba(255,255,255,.02); }
          .depth-3 td { background: rgba(255,255,255,.03); }
          .tag-key { font-family: monospace; color: #9aa; white-space: pre; }
          .vr-badge {
            display: inline-block; padding: 1px 5px; border-radius: 3px;
            font-size: 10px; font-weight: 600; letter-spacing: .5px;
          }
          .tag-name { color: #888; font-size: 11px; }
          .tag-value { color: #ccc; max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          .expand-arrow { color: #4a9eff; font-size: 10px; }
          .seq-item-header td { padding: 3px 10px; background: rgba(41,128,185,.08); color: #4a9eff; font-size: 11px; font-style: italic; }
          .tag-loading, .tag-error { display:flex; align-items:center; justify-content:center; padding:40px; color:#888; }
          .tag-error { color: #e74c3c; }
        `}</style>
      </div>
    </div>
  );
}
