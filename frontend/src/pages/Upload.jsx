// src/pages/Upload.jsx
// DICOM file upload — drag-and-drop or browse, shows per-file progress.
// Supports .dcm files and .zip archives of DICOM files.

import { useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";

function FileRow({ file, status, progress, error }) {
  const statusColor = {
    pending:    "#666",
    uploading:  "#4a9eff",
    done:       "#34d399",
    error:      "#e74c3c",
  }[status] || "#666";

  return (
    <div className="file-row">
      <div className="file-icon">📄</div>
      <div className="file-info">
        <div className="file-name">{file.name}</div>
        <div className="file-size">{fmtSize(file.size)}</div>
        {status === "uploading" && (
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
        )}
        {error && <div className="file-error">{error}</div>}
      </div>
      <div className="file-status" style={{ color: statusColor }}>
        {status === "uploading" && `${progress}%`}
        {status === "done"      && "✓"}
        {status === "error"     && "✗"}
        {status === "pending"   && "—"}
      </div>
    </div>
  );
}

export default function Upload() {
  const navigate             = useNavigate();
  const dropRef              = useRef(null);
  const inputRef             = useRef(null);
  const [files,    setFiles]    = useState([]); // {file, status, progress, error}
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [doneCount, setDoneCount] = useState(0);
  const [partition, setPartition] = useState("");

  const addFiles = useCallback((newFiles) => {
    const dcmFiles = Array.from(newFiles).filter(f =>
      f.name.endsWith(".dcm") || f.name.endsWith(".zip") || f.type === "application/zip"
    );
    if (dcmFiles.length === 0) {
      alert("Please select .dcm or .zip files");
      return;
    }
    setFiles(prev => [
      ...prev,
      ...dcmFiles.map(f => ({ file: f, status: "pending", progress: 0, error: null }))
    ]);
  }, []);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }, [addFiles]);

  const uploadAll = async () => {
    const pending = files.filter(f => f.status === "pending");
    if (pending.length === 0) return;
    setUploading(true);

    for (let i = 0; i < files.length; i++) {
      if (files[i].status !== "pending") continue;

      setFiles(prev => prev.map((f, idx) =>
        idx === i ? { ...f, status: "uploading", progress: 0 } : f
      ));

      try {
        const formData = new FormData();
        formData.append("file", files[i].file);
        if (partition) formData.append("partition", partition);

        await api.post("/api/instances/upload", formData, {
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress: (e) => {
            const pct = Math.round((e.loaded / e.total) * 100);
            setFiles(prev => prev.map((f, idx) =>
              idx === i ? { ...f, progress: pct } : f
            ));
          },
        });

        setFiles(prev => prev.map((f, idx) =>
          idx === i ? { ...f, status: "done", progress: 100 } : f
        ));
        setDoneCount(c => c + 1);

      } catch (e) {
        const msg = e.response?.data?.detail || "Upload failed";
        setFiles(prev => prev.map((f, idx) =>
          idx === i ? { ...f, status: "error", error: msg } : f
        ));
      }
    }
    setUploading(false);
  };

  const removeFile = (i) => {
    setFiles(prev => prev.filter((_, idx) => idx !== i));
  };

  const clearDone = () => {
    setFiles(prev => prev.filter(f => f.status !== "done"));
    setDoneCount(0);
  };

  const pending  = files.filter(f => f.status === "pending").length;
  const errCount = files.filter(f => f.status === "error").length;

  return (
    <div className="upload-page">
      <div className="page-hdr">
        <button className="back-btn" onClick={() => navigate(-1)}>← Back</button>
        <h1>Upload DICOM Files</h1>
      </div>

      {/* Drop zone */}
      <div
        ref={dropRef}
        className={`drop-zone ${dragging ? "drag-over" : ""}`}
        onDragEnter={() => setDragging(true)}
        onDragLeave={() => setDragging(false)}
        onDragOver={e => e.preventDefault()}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
      >
        <div className="drop-icon">📂</div>
        <div className="drop-text">
          Drop <code>.dcm</code> or <code>.zip</code> files here, or click to browse
        </div>
        <div className="drop-hint">Multiple files supported</div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".dcm,.zip"
          style={{ display: "none" }}
          onChange={e => addFiles(e.target.files)}
        />
      </div>

      {files.length > 0 && (
        <>
          {/* Controls */}
          <div className="upload-controls">
            <div className="summary">
              {files.length} file{files.length !== 1 ? "s" : ""} selected
              {doneCount > 0 && ` · ${doneCount} uploaded`}
              {errCount > 0  && ` · ${errCount} failed`}
            </div>
            <div className="control-right">
              {doneCount > 0 && (
                <button className="btn-clear" onClick={clearDone}>Clear Done</button>
              )}
              <button
                className="btn-upload"
                onClick={uploadAll}
                disabled={uploading || pending === 0}
              >
                {uploading ? "Uploading…" : `Upload ${pending} File${pending !== 1 ? "s" : ""}`}
              </button>
            </div>
          </div>

          {/* File list */}
          <div className="file-list">
            {files.map((f, i) => (
              <div key={i} style={{ position: "relative" }}>
                <FileRow {...f} />
                {f.status === "pending" && (
                  <button
                    className="remove-btn"
                    onClick={() => removeFile(i)}
                    title="Remove"
                  >×</button>
                )}
              </div>
            ))}
          </div>

          {doneCount > 0 && pending === 0 && errCount === 0 && (
            <div className="upload-success">
              ✓ All files uploaded successfully
              <button className="btn-worklist" onClick={() => navigate("/")}>
                Go to Worklist →
              </button>
            </div>
          )}
        </>
      )}

      <style>{`
        .upload-page { padding: 24px; max-width: 800px; margin: 0 auto; }
        .page-hdr { display: flex; align-items: center; gap: 14px; margin-bottom: 24px; }
        .page-hdr h1 { margin: 0; font-size: 22px; }
        .back-btn { background: none; border: 1px solid #2a2f3e; border-radius: 5px; color: #888; padding: 6px 12px; font-size: 13px; cursor: pointer; }
        .back-btn:hover { color: #ccc; }
        .drop-zone { border: 2px dashed #2a2f3e; border-radius: 12px; padding: 48px 24px; text-align: center; cursor: pointer; transition: all .2s; margin-bottom: 20px; }
        .drop-zone:hover, .drop-zone.drag-over { border-color: #4a9eff; background: #4a9eff0a; }
        .drop-icon { font-size: 40px; margin-bottom: 12px; }
        .drop-text { font-size: 15px; color: #ccc; }
        .drop-text code { background: #1e2330; padding: 2px 6px; border-radius: 3px; font-size: 13px; }
        .drop-hint { font-size: 12px; color: #666; margin-top: 6px; }
        .upload-controls { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .summary { font-size: 13px; color: #888; }
        .control-right { display: flex; gap: 8px; }
        .btn-clear { background: none; border: 1px solid #2a2f3e; color: #888; padding: 7px 14px; border-radius: 5px; font-size: 13px; cursor: pointer; }
        .btn-upload { background: #4a9eff; color: #fff; border: none; padding: 7px 18px; border-radius: 5px; font-size: 13px; cursor: pointer; font-weight: 600; }
        .btn-upload:disabled { opacity: .5; cursor: default; }
        .file-list { display: flex; flex-direction: column; gap: 4px; }
        .file-row { display: flex; align-items: center; gap: 12px; background: #1e2330; border-radius: 7px; padding: 10px 14px; }
        .file-icon { font-size: 18px; flex-shrink: 0; }
        .file-info { flex: 1; overflow: hidden; }
        .file-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .file-size { font-size: 11px; color: #666; margin-top: 2px; }
        .file-error { font-size: 11px; color: #e74c3c; margin-top: 2px; }
        .progress-track { height: 3px; background: #2a2f3e; border-radius: 2px; margin-top: 5px; overflow: hidden; }
        .progress-fill  { height: 100%; background: #4a9eff; transition: width .3s; }
        .file-status { font-size: 13px; font-weight: 700; min-width: 30px; text-align: right; }
        .remove-btn { position: absolute; right: 10px; top: 10px; background: none; border: none; color: #666; font-size: 18px; cursor: pointer; line-height: 1; }
        .remove-btn:hover { color: #e74c3c; }
        .upload-success { display: flex; align-items: center; gap: 16px; background: #0a2a1a; border: 1px solid #1a5a2a; border-radius: 8px; padding: 14px 18px; margin-top: 16px; color: #34d399; font-size: 14px; }
        .btn-worklist { background: none; border: 1px solid #34d399; color: #34d399; padding: 6px 14px; border-radius: 5px; font-size: 13px; cursor: pointer; margin-left: auto; }
      `}</style>
    </div>
  );
}

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
