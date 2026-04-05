// src/components/StudyActions.jsx
// ─────────────────────────────────────────────────────────────────
// Three reusable components used throughout the worklist and study views:
//
//   <ModalityBadge modality="CT" />
//   <SeriesThumbnails studyUID="..." seriesUID="..." />
//   <StudyContextMenu study={...} onAction={...} />

import { useState, useEffect, useRef } from "react";
import api from "../lib/api";

// ══════════════════════════════════════════════════════════════════
//  ModalityBadge
// ══════════════════════════════════════════════════════════════════

const MODALITY_STYLES = {
  CT:  { bg: "#1a3a5c", text: "#4a9eff", label: "CT"  },
  MR:  { bg: "#2a1a5c", text: "#9b6aff", label: "MR"  },
  CR:  { bg: "#1a3a2a", text: "#2ecc71", label: "CR"  },
  DX:  { bg: "#1a2a3a", text: "#3498db", label: "DX"  },
  US:  { bg: "#1a3a35", text: "#1abc9c", label: "US"  },
  NM:  { bg: "#3a2a1a", text: "#e67e22", label: "NM"  },
  PT:  { bg: "#3a1a1a", text: "#e74c3c", label: "PT"  },
  MG:  { bg: "#3a2e1a", text: "#f39c12", label: "MG"  },
  XA:  { bg: "#1a3a3a", text: "#16a085", label: "XA"  },
  RF:  { bg: "#2a1a3a", text: "#8e44ad", label: "RF"  },
  SC:  { bg: "#2a2a2a", text: "#95a5a6", label: "SC"  },
  OT:  { bg: "#2a2a2a", text: "#7f8c8d", label: "OT"  },
};

export function ModalityBadge({ modality, size = "md" }) {
  const style = MODALITY_STYLES[modality?.toUpperCase()] || MODALITY_STYLES.OT;
  const pad  = size === "sm" ? "2px 6px"  : "3px 9px";
  const font = size === "sm" ? "10px"     : "12px";
  return (
    <span style={{
      background: style.bg, color: style.text,
      padding: pad, borderRadius: 4,
      fontSize: font, fontWeight: 700,
      letterSpacing: ".5px", display: "inline-block",
    }}>
      {style.label || modality}
    </span>
  );
}


// ══════════════════════════════════════════════════════════════════
//  SeriesThumbnails
// ══════════════════════════════════════════════════════════════════

export function SeriesThumbnails({ studyUID, onSelectSeries }) {
  const [series, setSeries] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/wado/studies/${studyUID}/series`)
      .then(r => {
        setSeries(r.data || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [studyUID]);

  if (loading) return <div className="thumb-loading">Loading series…</div>;
  if (!series.length) return <div className="thumb-empty">No series</div>;

  return (
    <div className="thumb-strip">
      {series.map((s, i) => {
        const seriesUID    = s["0020000E"]?.Value?.[0];
        const modality     = s["00080060"]?.Value?.[0] || "??";
        const description  = s["0008103E"]?.Value?.[0] || "";
        const imageCount   = s["00201209"]?.Value?.[0] || "?";
        const seriesNumber = s["00200011"]?.Value?.[0] || i + 1;

        return (
          <div
            key={seriesUID || i}
            className="thumb-item"
            onClick={() => onSelectSeries?.(seriesUID)}
            title={description}
          >
            <div className="thumb-image">
              <img
                src={`/wado/studies/${studyUID}/series/${seriesUID}/thumbnail`}
                alt={description}
                onError={e => { e.target.style.display = "none"; }}
              />
              <div className="thumb-modality">
                <ModalityBadge modality={modality} size="sm" />
              </div>
            </div>
            <div className="thumb-info">
              <div className="thumb-series-num">Ser {seriesNumber}</div>
              <div className="thumb-desc">{description || modality}</div>
              <div className="thumb-count">{imageCount} img</div>
            </div>
          </div>
        );
      })}
      <style>{`
        .thumb-strip { display:flex; gap:8px; overflow-x:auto; padding:8px 0; }
        .thumb-item {
          flex-shrink:0; width:96px; cursor:pointer; border-radius:6px;
          border:1px solid #2a2f3e; overflow:hidden; background:#1a1f2e;
          transition:border-color .15s;
        }
        .thumb-item:hover { border-color:#4a9eff; }
        .thumb-image {
          width:96px; height:96px; background:#0e1118;
          position:relative; display:flex; align-items:center; justify-content:center;
          overflow:hidden;
        }
        .thumb-image img { width:100%; height:100%; object-fit:cover; }
        .thumb-modality { position:absolute; top:4px; left:4px; }
        .thumb-info { padding:4px 6px; }
        .thumb-series-num { font-size:10px; color:#666; }
        .thumb-desc { font-size:11px; color:#ccc; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .thumb-count { font-size:10px; color:#888; margin-top:2px; }
        .thumb-loading, .thumb-empty { color:#666; font-size:12px; padding:8px; }
      `}</style>
    </div>
  );
}


// ══════════════════════════════════════════════════════════════════
//  StudyContextMenu
// ══════════════════════════════════════════════════════════════════
// Right-click (or ⋮ button) context menu for a study row.
// Actions: Open in OHIF, View tags, Send (C-MOVE), Anonymize,
//          Compress, Delete, Burn to CD.

export function StudyContextMenu({ study, position, onClose, onAction }) {
  const menuRef = useRef(null);

  useEffect(() => {
    const handler = e => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  const handle = (action) => {
    onAction(action, study);
    onClose();
  };

  const items = [
    { id: "ohif",       icon: "🖥",  label: "Open in OHIF Viewer",  divider: false },
    { id: "tags",       icon: "🏷",  label: "Browse DICOM Tags",    divider: false },
    { id: "send",       icon: "📤",  label: "Send to AE…",          divider: true  },
    { id: "anonymize",  icon: "🔒",  label: "Anonymize…",           divider: false },
    { id: "compress",   icon: "📦",  label: "Compress…",            divider: false },
    { id: "burn",       icon: "💿",  label: "Add to Burn Queue",    divider: true  },
    { id: "delete",     icon: "🗑",  label: "Delete Study",         divider: false, danger: true },
  ];

  // Clamp position to viewport
  const style = {
    position: "fixed",
    left:  Math.min(position.x, window.innerWidth  - 220),
    top:   Math.min(position.y, window.innerHeight - 300),
    zIndex: 8000,
  };

  return (
    <div ref={menuRef} className="ctx-menu" style={style}>
      <div className="ctx-study-label">
        {study.patient_name || "Unknown"} — {study.study_date || ""}
      </div>
      {items.map(item => (
        <div key={item.id}>
          {item.divider && <div className="ctx-divider" />}
          <button
            className={`ctx-item ${item.danger ? "ctx-danger" : ""}`}
            onClick={() => handle(item.id)}
          >
            <span className="ctx-icon">{item.icon}</span>
            {item.label}
          </button>
        </div>
      ))}
      <style>{`
        .ctx-menu {
          background: #1e2436; border: 1px solid #2a2f3e;
          border-radius: 8px; padding: 4px 0; min-width: 200px;
          box-shadow: 0 8px 32px rgba(0,0,0,.5);
          user-select: none;
        }
        .ctx-study-label {
          font-size: 11px; color: #666; padding: 6px 14px 4px;
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
          border-bottom: 1px solid #2a2f3e; margin-bottom: 4px;
        }
        .ctx-item {
          display: flex; align-items: center; gap: 10px;
          width: 100%; background: none; border: none;
          color: #ccc; padding: 7px 14px; cursor: pointer;
          font-size: 13px; text-align: left;
        }
        .ctx-item:hover { background: rgba(255,255,255,.06); color: #fff; }
        .ctx-danger { color: #e74c3c !important; }
        .ctx-danger:hover { background: rgba(231,76,60,.1) !important; }
        .ctx-icon { font-size: 14px; width: 18px; text-align: center; }
        .ctx-divider { border-top: 1px solid #2a2f3e; margin: 4px 0; }
      `}</style>
    </div>
  );
}


// ══════════════════════════════════════════════════════════════════
//  SendToAEModal  (used by StudyContextMenu "send" action)
// ══════════════════════════════════════════════════════════════════

export function SendToAEModal({ study, onClose }) {
  const [ae,   setAe]   = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("104");
  const [sending, setSending] = useState(false);
  const [result,  setResult]  = useState(null);

  const send = async () => {
    if (!ae || !host) return;
    setSending(true);
    try {
      const r = await api.post(`/api/studies/${study.study_instance_uid}/send`, {
        ae_title: ae, host, port: parseInt(port),
      });
      setResult({ success: true, detail: `Sent ${r.data.sent} instances` });
    } catch (e) {
      setResult({ success: false, detail: e.response?.data?.detail || e.message });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ width: 380 }} onClick={e => e.stopPropagation()}>
        <h3>Send Study to AE</h3>
        <p style={{ fontSize: 12, color: "#888", margin: "0 0 16px" }}>
          {study.patient_name} — {study.study_date}
        </p>

        <label style={{ fontSize: 12, color: "#888" }}>Destination AE Title</label>
        <input value={ae} onChange={e => setAe(e.target.value.toUpperCase())}
          style={{ width: "100%", marginBottom: 8 }} placeholder="PACS_AE" />

        <label style={{ fontSize: 12, color: "#888" }}>Host / IP Address</label>
        <input value={host} onChange={e => setHost(e.target.value)}
          style={{ width: "100%", marginBottom: 8 }} placeholder="192.168.1.100" />

        <label style={{ fontSize: 12, color: "#888" }}>Port</label>
        <input value={port} onChange={e => setPort(e.target.value)}
          style={{ width: 100, marginBottom: 16 }} type="number" />

        {result && (
          <div style={{
            padding: "8px 12px", borderRadius: 5, marginBottom: 12,
            background: result.success ? "#0d2d1a" : "#2d0d0d",
            color: result.success ? "#2ecc71" : "#e74c3c",
            fontSize: 13,
          }}>
            {result.detail}
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button className="btn-secondary" onClick={onClose}>Close</button>
          {!result && (
            <button className="btn-primary" onClick={send} disabled={sending}>
              {sending ? "Sending…" : "Send"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
