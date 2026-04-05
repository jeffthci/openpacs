// src/pages/OHIFViewer.jsx
// ─────────────────────────────────────────────────────────────────
// Launches OHIF Viewer in an iframe pointed at our DICOMweb backend.
// Can open a specific study or show the full worklist.
//
// Usage:
//   /ohif                    → OHIF full worklist mode
//   /ohif?studyUID=1.2.3...  → OHIF opens specific study
//
// Setup:
//   1. npm install inside /ohif-viewer or use the CDN version
//   2. Set VITE_OHIF_URL in .env (default: http://localhost:3000)
//
// OHIF config file (ohif-config.js) is generated and served at /ohif-config.js

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

const OHIF_URL = import.meta.env.VITE_OHIF_URL || "http://localhost:3000";
const WADO_ROOT = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function OHIFViewer() {
  const [searchParams] = useSearchParams();
  const studyUID = searchParams.get("studyUID");

  // Build OHIF URL with DICOMweb datasource embedded as query params
  // OHIF supports loading a datasource config via URL params
  const buildUrl = () => {
    const base = OHIF_URL;

    if (studyUID) {
      // Direct study viewer URL
      return `${base}/viewer?StudyInstanceUIDs=${studyUID}`;
    }
    // Full worklist
    return `${base}/`;
  };

  return (
    <div style={{ height: "100vh", width: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{
        height: 40, background: "#141820", display: "flex",
        alignItems: "center", padding: "0 16px", gap: 12,
        borderBottom: "1px solid #2a2f3e", flexShrink: 0
      }}>
        <span style={{ color: "#4a9eff", fontWeight: 600, fontSize: 14 }}>OHIF Viewer</span>
        {studyUID && (
          <span style={{ color: "#888", fontSize: 12 }}>
            Study: {studyUID.slice(0, 30)}…
          </span>
        )}
        <a
          href="/ohif-config"
          target="_blank"
          style={{ color: "#888", fontSize: 11, marginLeft: "auto" }}
        >
          Config ↗
        </a>
      </div>
      <iframe
        src={buildUrl()}
        style={{ flex: 1, border: "none", width: "100%" }}
        title="OHIF DICOM Viewer"
        allow="fullscreen"
      />
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
// OHIF Configuration
// ─────────────────────────────────────────────────────────────────
// Add this route to main.py to serve the OHIF config:
//
//   @app.get("/ohif-config.js")
//   def ohif_config():
//       return Response(
//           content=build_ohif_config(),
//           media_type="application/javascript"
//       )
//
// Python function:
//
//   def build_ohif_config():
//       base = settings.WADO_BASE_URL
//       return f"""
//   window.config = {{
//     routerBasename: '/',
//     extensions: [],
//     modes: [],
//     customizationService: {{}},
//     defaultDataSourceName: 'dicomweb',
//     dataSources: [{{
//       namespace: '@ohif/extension-default.dataSourcesModule.dicomweb',
//       sourceName: 'dicomweb',
//       configuration: {{
//         friendlyName: 'OpenPACS DICOMweb',
//         name: 'DCM4CHEE',
//         wadoUriRoot:  '{base}/wado',
//         qidoRoot:     '{base}/wado',
//         wadoRoot:     '{base}/wado',
//         qidoSupportsIncludeField: true,
//         imageRendering: 'wadors',
//         thumbnailRendering: 'wadors',
//         enableStudyLazyLoad: true,
//         supportsFuzzyMatching: true,
//         supportsWildcard: true,
//         staticWado: false,
//         singlepart: false,
//       }},
//     }}],
//   }};
//   """
