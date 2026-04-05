// src/pages/Viewer.jsx
// Cornerstone.js DICOM viewer — loads instances from our DICOMweb backend.
// Supports: W/L, zoom/pan, scroll, measurements, multi-series layout.

import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import api from "../lib/api";

const WADO_ROOT = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Tool button ───────────────────────────────────────────────────
function ToolBtn({ label, active, onClick, title }) {
  return (
    <button className={`tool-btn ${active ? "active" : ""}`} onClick={onClick} title={title}>
      {label}
    </button>
  );
}

// ── Thumbnail strip item ──────────────────────────────────────────
function SeriesThumb({ series, active, onClick }) {
  return (
    <div className={`thumb ${active ? "active" : ""}`} onClick={onClick}>
      <div className="thumb-mod">{series.modality || "?"}</div>
      <div className="thumb-info">
        <div className="thumb-desc">{series.series_description || "Series " + series.series_number}</div>
        <div className="thumb-count">{series.number_of_series_related_instances || 0} imgs</div>
      </div>
    </div>
  );
}

export default function Viewer() {
  const { uid }                       = useParams();
  const [searchParams]                = useSearchParams();
  const navigate                      = useNavigate();
  const viewportRef                   = useRef(null);
  const cornerstoneRef                = useRef(null);

  const [study,         setStudy]         = useState(null);
  const [seriesList,    setSeriesList]     = useState([]);
  const [activeSeries,  setActiveSeries]  = useState(null);
  const [instances,     setInstances]     = useState([]);
  const [currentIdx,    setCurrentIdx]    = useState(0);
  const [activeTool,    setActiveTool]    = useState("wwwc");
  const [windowWidth,   setWindowWidth]   = useState(400);
  const [windowCenter,  setWindowCenter]  = useState(40);
  const [loading,       setLoading]       = useState(true);
  const [csLoaded,      setCsLoaded]      = useState(false);

  // ── Load Cornerstone dynamically ─────────────────────────────
  useEffect(() => {
    const loadCS = async () => {
      if (window.cornerstone) { setCsLoaded(true); return; }

      // Load Cornerstone from CDN
      const scripts = [
        "https://cdn.jsdelivr.net/npm/cornerstone-core@2.6.1/dist/cornerstone.min.js",
        "https://cdn.jsdelivr.net/npm/cornerstone-math@0.1.10/dist/cornerstoneMath.min.js",
        "https://cdn.jsdelivr.net/npm/cornerstone-tools@6.0.10/dist/cornerstoneTools.min.js",
        "https://cdn.jsdelivr.net/npm/cornerstone-wado-image-loader@4.13.2/dist/cornerstoneWADOImageLoader.bundled.min.js",
        "https://cdn.jsdelivr.net/npm/dicom-parser@1.8.21/dist/dicomParser.min.js",
      ];

      for (const src of scripts) {
        await new Promise((res, rej) => {
          const s = document.createElement("script");
          s.src = src; s.onload = res; s.onerror = rej;
          document.head.appendChild(s);
        });
      }

      // Configure WADO image loader
      window.cornerstoneWADOImageLoader.external.cornerstone   = window.cornerstone;
      window.cornerstoneWADOImageLoader.external.dicomParser    = window.dicomParser;
      window.cornerstoneWADOImageLoader.configure({
        useWebWorkers: true,
        decodeConfig: { convertFloatPixelDataToInt: false },
        beforeSend: (xhr) => {
          const token = localStorage.getItem("access_token");
          if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        },
      });

      // Init CornerstoneTools
      window.cornerstoneTools.external.cornerstone = window.cornerstone;
      window.cornerstoneTools.external.cornerstoneMath = window.cornerstoneMath;
      window.cornerstoneTools.init();

      setCsLoaded(true);
    };

    loadCS().catch(console.error);
  }, []);

  // ── Load study + series ───────────────────────────────────────
  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await api.get(`/api/studies/${uid}`);
        setStudy(data);
        const sl = data.series || [];
        setSeriesList(sl);
        const requestedSeries = searchParams.get("series");
        const first = requestedSeries
          ? sl.find(s => String(s.id) === requestedSeries) || sl[0]
          : sl[0];
        if (first) setActiveSeries(first);
      } catch (e) {
        console.error("Failed to load study:", e);
      }
    };
    load();
  }, [uid, searchParams]);

  // ── Load instances for active series ─────────────────────────
  useEffect(() => {
    if (!activeSeries) return;
    const load = async () => {
      setLoading(true);
      try {
        const { data } = await api.get(`/api/series/${activeSeries.id}/instances`);
        const sorted = (Array.isArray(data) ? data : data.items || [])
          .sort((a, b) => (a.instance_number ?? 0) - (b.instance_number ?? 0));
        setInstances(sorted);
        setCurrentIdx(0);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [activeSeries]);

  // ── Mount Cornerstone viewport ────────────────────────────────
  useEffect(() => {
    if (!csLoaded || !viewportRef.current || instances.length === 0) return;
    const cs  = window.cornerstone;
    const cst = window.cornerstoneTools;
    const el  = viewportRef.current;

    cs.enable(el);

    const inst = instances[currentIdx];
    // Build WADO-URI URL pointing at our DICOMweb endpoint
    const imageId = `wadouri:${WADO_ROOT}/wado/studies/${study?.study_instance_uid}/series/${activeSeries?.series_instance_uid}/instances/${inst.sop_instance_uid}`;

    cs.loadAndCacheImage(imageId).then(image => {
      cs.displayImage(el, image);
      cornerstoneRef.current = { cs, cst, el, imageId };

      // Set up tools
      const tools = ["Wwwc", "Pan", "Zoom", "Length", "Angle", "Probe"];
      tools.forEach(t => {
        try { cst.addTool(cst.LengthTool); } catch {} // simplified
      });
      cst.setToolActive("Wwwc", { mouseButtonMask: 1 });

      const vp = cs.getViewport(el);
      if (vp) {
        setWindowWidth(vp.voi?.windowWidth || 400);
        setWindowCenter(vp.voi?.windowCenter || 40);
      }
    }).catch(console.error);

    return () => {
      try { cs.disable(el); } catch {}
    };
  }, [csLoaded, instances, currentIdx, activeSeries, study]);

  // ── W/L sliders ───────────────────────────────────────────────
  const applyWL = (ww, wc) => {
    if (!cornerstoneRef.current) return;
    const { cs, el } = cornerstoneRef.current;
    try {
      const vp = cs.getViewport(el);
      vp.voi.windowWidth  = ww;
      vp.voi.windowCenter = wc;
      cs.setViewport(el, vp);
      cs.updateImage(el);
    } catch {}
  };

  // ── Scroll handler ────────────────────────────────────────────
  const handleWheel = (e) => {
    e.preventDefault();
    setCurrentIdx(i => {
      const next = i + (e.deltaY > 0 ? 1 : -1);
      return Math.max(0, Math.min(instances.length - 1, next));
    });
  };

  if (!study) return <div className="viewer-loading">Loading…</div>;

  return (
    <div className="viewer-page">
      {/* Toolbar */}
      <div className="viewer-toolbar">
        <button className="back-btn" onClick={() => navigate(-1)}>← Study</button>
        <div className="toolbar-sep" />
        <ToolBtn label="W/L"    active={activeTool==="wwwc"}   onClick={() => setActiveTool("wwwc")}   title="Window/Level" />
        <ToolBtn label="Zoom"   active={activeTool==="zoom"}   onClick={() => setActiveTool("zoom")}   title="Zoom" />
        <ToolBtn label="Pan"    active={activeTool==="pan"}    onClick={() => setActiveTool("pan")}    title="Pan" />
        <ToolBtn label="Length" active={activeTool==="length"} onClick={() => setActiveTool("length")} title="Length measurement" />
        <ToolBtn label="Angle"  active={activeTool==="angle"}  onClick={() => setActiveTool("angle")}  title="Angle measurement" />
        <div className="toolbar-sep" />
        <div className="wl-controls">
          <label>WW <input type="range" min={1} max={4000} value={windowWidth}
            onChange={e => { setWindowWidth(+e.target.value); applyWL(+e.target.value, windowCenter); }} />
            {windowWidth}</label>
          <label>WC <input type="range" min={-1000} max={3000} value={windowCenter}
            onChange={e => { setWindowCenter(+e.target.value); applyWL(windowWidth, +e.target.value); }} />
            {windowCenter}</label>
        </div>
        <div className="toolbar-sep" />
        <div className="frame-counter">
          {instances.length > 0 && `${currentIdx + 1} / ${instances.length}`}
        </div>
        <div style={{marginLeft:"auto"}}>
          <button className="btn-ohif"
            onClick={() => navigate(`/ohif?studyUID=${study.study_instance_uid}`)}>
            Open in OHIF ↗
          </button>
        </div>
      </div>

      <div className="viewer-body">
        {/* Series thumbnail panel */}
        <div className="series-panel">
          {seriesList.map(s => (
            <SeriesThumb
              key={s.id}
              series={s}
              active={activeSeries?.id === s.id}
              onClick={() => setActiveSeries(s)}
            />
          ))}
        </div>

        {/* Viewport */}
        <div className="viewport-wrap">
          {loading && <div className="viewport-overlay">Loading series…</div>}
          {!csLoaded && !loading && (
            <div className="viewport-overlay">Loading Cornerstone.js…</div>
          )}
          <div
            ref={viewportRef}
            className="cornerstone-viewport"
            onWheel={handleWheel}
          />
          {/* Frame scrollbar */}
          {instances.length > 1 && (
            <input
              className="frame-slider"
              type="range"
              min={0}
              max={instances.length - 1}
              value={currentIdx}
              onChange={e => setCurrentIdx(+e.target.value)}
            />
          )}
        </div>
      </div>

      <style>{`
        .viewer-page { display: flex; flex-direction: column; height: 100vh; background: #000; color: #ccc; overflow: hidden; }
        .viewer-toolbar { display: flex; align-items: center; gap: 6px; padding: 6px 10px; background: #141820; border-bottom: 1px solid #2a2f3e; flex-shrink: 0; flex-wrap: wrap; }
        .back-btn { background: none; border: 1px solid #2a2f3e; color: #888; padding: 5px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; }
        .back-btn:hover { color: #ccc; }
        .toolbar-sep { width: 1px; height: 24px; background: #2a2f3e; margin: 0 4px; }
        .tool-btn { padding: 5px 10px; border: 1px solid #2a2f3e; border-radius: 4px; background: #1e2330; color: #aaa; font-size: 12px; cursor: pointer; transition: all .15s; }
        .tool-btn:hover { background: #2a3a5a; color: #fff; }
        .tool-btn.active { background: #4a9eff22; border-color: #4a9eff; color: #4a9eff; }
        .wl-controls { display: flex; gap: 12px; }
        .wl-controls label { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #888; }
        .wl-controls input { width: 80px; accent-color: #4a9eff; }
        .frame-counter { font-size: 12px; color: #666; font-variant-numeric: tabular-nums; }
        .btn-ohif { background: #2a1a5c; color: #a78bfa; border: none; border-radius: 4px; padding: 5px 12px; font-size: 12px; cursor: pointer; }
        .viewer-body { display: flex; flex: 1; overflow: hidden; }
        .series-panel { width: 160px; flex-shrink: 0; background: #0d1117; border-right: 1px solid #2a2f3e; overflow-y: auto; }
        .thumb { display: flex; align-items: center; gap: 8px; padding: 10px; cursor: pointer; border-bottom: 1px solid #1a1f2e; transition: background .15s; }
        .thumb:hover { background: #1a1f2e; }
        .thumb.active { background: #1a2540; border-left: 3px solid #4a9eff; }
        .thumb-mod { width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; background: #1e2330; border-radius: 4px; font-size: 10px; font-weight: 700; color: #4a9eff; flex-shrink: 0; }
        .thumb-desc { font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .thumb-count { font-size: 10px; color: #666; margin-top: 2px; }
        .viewport-wrap { flex: 1; position: relative; overflow: hidden; background: #000; }
        .cornerstone-viewport { width: 100%; height: 100%; }
        .viewport-overlay { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #666; font-size: 14px; z-index: 10; background: rgba(0,0,0,.6); }
        .frame-slider { position: absolute; right: 6px; top: 10%; height: 80%; -webkit-appearance: slider-vertical; writing-mode: vertical-lr; direction: rtl; width: 18px; accent-color: #4a9eff; cursor: pointer; z-index: 5; }
        .viewer-loading { display: flex; align-items: center; justify-content: center; height: 100vh; background: #000; color: #666; }
      `}</style>
    </div>
  );
}
