// ohif-config.js
// ─────────────────────────────────────────────────────────────────
// OHIF Viewer configuration — points OHIF at our DICOMweb backend.
//
// DEPLOYMENT:
//   1. Update WADO_ROOT to your server's LAN/public address
//   2. Mount this file into the OHIF container:
//      docker run -v ./ohif-config.js:/usr/share/nginx/html/app-config.js ohif/app
//   3. Or reference via OHIF's APP_CONFIG env var
//
// ─────────────────────────────────────────────────────────────────

const WADO_ROOT = "http://localhost:8000/wado";  // ← change this

window.config = {
  routerBasename: "/",

  // Show the worklist on load
  defaultDataSourceName: "dicomweb",

  dataSources: [
    {
      namespace: "@ohif/extension-default.dataSourcesModule.dicomweb",
      sourceName: "dicomweb",
      configuration: {
        friendlyName:  "OpenPACS",
        name:          "OpenPACS",

        // All three endpoints point to our FastAPI server
        wadoUriRoot:   WADO_ROOT,
        qidoRoot:      WADO_ROOT,
        wadoRoot:      WADO_ROOT,

        // DICOMweb features our server supports
        qidoSupportsIncludeField: true,
        supportsReject:           false,
        imageRendering:           "wadors",
        thumbnailRendering:       "wadors",
        enableStudyLazyLoad:      true,
        supportsFuzzyMatching:    true,
        supportsWildcard:         true,
        staticWado:               false,
        singlepart:               false,

        // Number of concurrent instance requests
        requestTransferSyntaxUID: "1.2.840.10008.1.2.1",
        acceptHeader: [
          "multipart/related; type=\"application/octet-stream\"; transfer-syntax=*",
        ],
      },
    },
  ],

  // ── Customisation ──────────────────────────────────────────────
  customizationService: {
    // Custom logo — remove to use OHIF default
    // "ohif.leftPanel.logo": {
    //   $transform: { referenceId: "ohif.customLogoComponent" }
    // }
  },

  // ── Hotkeys ───────────────────────────────────────────────────
  hotkeys: [
    { commandName: "incrementActiveViewport", label: "Next Viewport",     keys: ["right"] },
    { commandName: "decrementActiveViewport", label: "Previous Viewport", keys: ["left"]  },
    { commandName: "rotateViewportCW",        label: "Rotate CW",         keys: ["r"]     },
    { commandName: "flipViewportHorizontal",  label: "Flip H",            keys: ["h"]     },
    { commandName: "flipViewportVertical",    label: "Flip V",            keys: ["v"]     },
    { commandName: "scaleUpViewport",         label: "Zoom In",           keys: ["+"]     },
    { commandName: "scaleDownViewport",       label: "Zoom Out",          keys: ["-"]     },
    { commandName: "fitViewportToWindow",     label: "Fit to Window",     keys: ["="]     },
    { commandName: "resetViewport",           label: "Reset",             keys: ["space"] },
    { commandName: "invertViewport",          label: "Invert",            keys: ["i"]     },
    { commandName: "nextImage",               label: "Next Image",        keys: ["down"]  },
    { commandName: "previousImage",           label: "Prev Image",        keys: ["up"]    },
  ],
};
