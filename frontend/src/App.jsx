// src/App.jsx
// Complete routing configuration — replace your existing App.jsx
// Adds: Admin, Partitions, AuditLog, OHIFViewer routes + updated nav

import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import { useState } from "react";

// Existing pages (keep yours)
import Login        from "./pages/Login";
import Worklist     from "./pages/Worklist";
import Study        from "./pages/Study";
import Viewer       from "./pages/Viewer";
import Report       from "./pages/Report";
import Patients     from "./pages/Patients";
import Upload       from "./pages/Upload";
import Burn         from "./pages/Burn";

// New pages
import Admin        from "./pages/Admin";
import Partitions   from "./pages/Partitions";
import AuditLog     from "./pages/AuditLog";
import OHIFViewer   from "./pages/OHIFViewer";
import Users        from "./pages/Users";
import Analytics    from "./pages/Analytics";
import WorklistMgmt from "./pages/WorklistMgmt";

import { useAuth } from "./hooks/useAuth";

function Layout({ children }) {
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const isAdmin = user?.role === "admin";

  return (
    <div className={`app-shell ${collapsed ? "nav-collapsed" : ""}`}>
      {/* ── Sidebar ─────────────────────────────────────────── */}
      <nav className="sidebar">
        <div className="sidebar-top">
          <div className="sidebar-logo" onClick={() => setCollapsed(c => !c)}>
            {collapsed ? "⊞" : <><span className="logo-text">Open</span><span className="logo-accent">PACS</span></>}
          </div>
        </div>

        <div className="nav-section">
          <span className="nav-label">Imaging</span>
          <NavLink to="/"        end className="nav-item"><span className="nav-icon">☰</span><span className="nav-text">Worklist</span></NavLink>
          <NavLink to="/patients"    className="nav-item"><span className="nav-icon">👤</span><span className="nav-text">Patients</span></NavLink>
          <NavLink to="/worklist-mgmt" className="nav-item"><span className="nav-icon">📅</span><span className="nav-text">Schedule</span></NavLink>
          <NavLink to="/upload"      className="nav-item"><span className="nav-icon">↑</span><span className="nav-text">Upload</span></NavLink>
          <NavLink to="/burn"        className="nav-item"><span className="nav-icon">💿</span><span className="nav-text">Burn CD</span></NavLink>
        </div>

        <div className="nav-section">
          <span className="nav-label">Viewers</span>
          <NavLink to="/ohif" className="nav-item"><span className="nav-icon">🖥</span><span className="nav-text">OHIF Viewer</span></NavLink>
        </div>

        {isAdmin && (
          <div className="nav-section">
            <span className="nav-label">Administration</span>
            <NavLink to="/admin"      className="nav-item"><span className="nav-icon">⚙</span><span className="nav-text">Server Admin</span></NavLink>
            <NavLink to="/partitions" className="nav-item"><span className="nav-icon">⊞</span><span className="nav-text">Partitions</span></NavLink>
            <NavLink to="/users"      className="nav-item"><span className="nav-icon">👥</span><span className="nav-text">Users</span></NavLink>
            <NavLink to="/audit"      className="nav-item"><span className="nav-icon">📋</span><span className="nav-text">Audit Log</span></NavLink>
            <NavLink to="/analytics"  className="nav-item"><span className="nav-icon">📊</span><span className="nav-text">Analytics</span></NavLink>
          </div>
        )}

        <div className="sidebar-bottom">
          <div className="user-info">
            <span className="user-avatar">{user?.username?.[0]?.toUpperCase() || "?"}</span>
            <div className="user-details">
              <span className="user-name">{user?.username}</span>
              <span className="user-role">{user?.role}</span>
            </div>
          </div>
          <button className="logout-btn" onClick={logout}>Sign out</button>
        </div>
      </nav>

      {/* ── Main content ─────────────────────────────────────── */}
      <main className="main-content">
        {children}
      </main>
    </div>
  );
}

function ProtectedRoute({ children, adminOnly = false }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="app-loading">Loading…</div>;
  if (!user)   return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />

        {/* OHIF is full-screen, no sidebar */}
        <Route path="/ohif" element={
          <ProtectedRoute><OHIFViewer /></ProtectedRoute>
        } />

        {/* All other routes use Layout sidebar */}
        <Route path="/*" element={
          <ProtectedRoute>
            <Layout>
              <Routes>
                <Route path="/"             element={<Worklist />} />
                <Route path="/patients"     element={<Patients />} />
                <Route path="/study/:uid"   element={<Study />} />
                <Route path="/viewer/:uid"  element={<Viewer />} />
                <Route path="/report/:uid"  element={<Report />} />
                <Route path="/upload"       element={<Upload />} />
                <Route path="/burn"         element={<Burn />} />
                <Route path="/admin"        element={<ProtectedRoute adminOnly><Admin /></ProtectedRoute>} />
                <Route path="/partitions"   element={<ProtectedRoute adminOnly><Partitions /></ProtectedRoute>} />
                <Route path="/audit"        element={<ProtectedRoute adminOnly><AuditLog /></ProtectedRoute>} />
                <Route path="/users"        element={<ProtectedRoute adminOnly><Users /></ProtectedRoute>} />
                <Route path="/analytics"    element={<ProtectedRoute adminOnly><Analytics /></ProtectedRoute>} />
                <Route path="/worklist-mgmt" element={<ProtectedRoute><WorklistMgmt /></ProtectedRoute>} />
              </Routes>
            </Layout>
          </ProtectedRoute>
        } />
      </Routes>

      <style>{`
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
          --bg:   #0f1117;
          --bg2:  #1a1f2e;
          --bg3:  #1e2436;
          --border: #2a3040;
          --text:   #d0d8e8;
          --muted:  #6a7d9e;
          --accent: #4a9eff;
          --sidebar-w: 200px;
          --sidebar-collapsed: 52px;
        }
        body { background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; font-size: 14px; }

        .app-shell { display: flex; height: 100vh; overflow: hidden; }

        /* ── Sidebar ─────────────────────────────────────── */
        .sidebar {
          width: var(--sidebar-w);
          background: var(--bg2);
          border-right: 1px solid var(--border);
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
          transition: width .2s;
          overflow: hidden;
        }
        .nav-collapsed .sidebar { width: var(--sidebar-collapsed); }

        .sidebar-top { padding: 12px; }
        .sidebar-logo {
          font-size: 17px; font-weight: 700; cursor: pointer;
          padding: 8px; border-radius: 6px; transition: background .15s;
          white-space: nowrap;
        }
        .sidebar-logo:hover { background: var(--bg3); }
        .logo-text   { color: var(--text); }
        .logo-accent { color: var(--accent); }

        .nav-section { padding: 4px 0; }
        .nav-label {
          display: block; font-size: 10px; font-weight: 600;
          color: var(--muted); text-transform: uppercase; letter-spacing: .8px;
          padding: 8px 14px 4px; white-space: nowrap; overflow: hidden;
        }
        .nav-collapsed .nav-label { opacity: 0; }

        .nav-item {
          display: flex; align-items: center; gap: 10px;
          padding: 8px 12px; border-radius: 6px; margin: 1px 6px;
          color: var(--muted); text-decoration: none; font-size: 13px;
          transition: background .15s, color .15s; white-space: nowrap;
        }
        .nav-item:hover { background: var(--bg3); color: var(--text); }
        .nav-item.active { background: var(--accent)22; color: var(--accent); }
        .nav-icon  { font-size: 14px; min-width: 18px; text-align: center; }
        .nav-text  { }
        .nav-collapsed .nav-text { display: none; }

        .sidebar-bottom { margin-top: auto; padding: 12px; border-top: 1px solid var(--border); }
        .user-info { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
        .user-avatar { width: 28px; height: 28px; border-radius: 50%; background: var(--accent)44; color: var(--accent); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 12px; flex-shrink: 0; }
        .user-details { overflow: hidden; }
        .user-name { display: block; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .user-role { display: block; font-size: 11px; color: var(--muted); text-transform: capitalize; }
        .nav-collapsed .user-details { display: none; }
        .logout-btn { width: 100%; background: none; border: 1px solid var(--border); border-radius: 5px; color: var(--muted); padding: 6px; cursor: pointer; font-size: 12px; transition: all .15s; }
        .logout-btn:hover { border-color: #e74c3c44; color: #e74c3c; }
        .nav-collapsed .logout-btn { padding: 6px 4px; font-size: 10px; }

        /* ── Main content ─────────────────────────────────── */
        .main-content { flex: 1; overflow-y: auto; height: 100vh; }
        .app-loading { display: flex; align-items: center; justify-content: center; height: 100vh; color: var(--muted); }
      `}</style>
    </BrowserRouter>
  );
}
