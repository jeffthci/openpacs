// src/pages/Users.jsx
// User management — admin only.
// Create users, set roles, activate/deactivate, reset passwords.

import { useState, useEffect } from "react";
import api from "../lib/api";
import { useAuth } from "../hooks/useAuth";

const ROLES = ["viewer", "technician", "radiologist", "admin"];
const ROLE_COLORS = {
  viewer:       "#666",
  technician:   "#34d399",
  radiologist:  "#4a9eff",
  admin:        "#f87171",
};

function UserModal({ user, onSave, onClose }) {
  const isNew = !user?.id;
  const [form, setForm] = useState({
    username: user?.username || "",
    email:    user?.email    || "",
    role:     user?.role     || "viewer",
    password: "",
    confirm:  "",
    is_active: user?.is_active ?? true,
  });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setError(null);
    if (isNew && !form.password) { setError("Password required for new users"); return; }
    if (form.password && form.password !== form.confirm) { setError("Passwords do not match"); return; }
    setSaving(true);
    try {
      await onSave(form);
    } catch (e) {
      setError(e.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{isNew ? "New User" : `Edit — ${user.username}`}</h3>

        {error && <div className="modal-error">{error}</div>}

        <label>Username</label>
        <input value={form.username} onChange={e => setForm(f => ({...f, username: e.target.value}))} />

        <label>Email</label>
        <input type="email" value={form.email} onChange={e => setForm(f => ({...f, email: e.target.value}))} />

        <label>Role</label>
        <select value={form.role} onChange={e => setForm(f => ({...f, role: e.target.value}))}>
          {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
        </select>

        <label>{isNew ? "Password" : "New password (leave blank to keep current)"}</label>
        <input type="password" value={form.password}
          onChange={e => setForm(f => ({...f, password: e.target.value}))} />

        {form.password && (
          <>
            <label>Confirm password</label>
            <input type="password" value={form.confirm}
              onChange={e => setForm(f => ({...f, confirm: e.target.value}))} />
          </>
        )}

        {!isNew && (
          <label style={{ display:"flex", alignItems:"center", gap:8, marginTop:12, cursor:"pointer" }}>
            <input type="checkbox" checked={form.is_active}
              onChange={e => setForm(f => ({...f, is_active: e.target.checked}))} />
            Active
          </label>
        )}

        <div className="modal-actions">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={submit} disabled={saving}>
            {saving ? "Saving…" : isNew ? "Create User" : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Users() {
  const { user: currentUser } = useAuth();
  const [users,        setUsers]        = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState(null);
  const [showModal,    setShowModal]    = useState(false);
  const [editingUser,  setEditingUser]  = useState(null);
  const [search,       setSearch]       = useState("");

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/auth/users");
      setUsers(data);
    } catch (e) {
      setError("Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, []);

  const saveUser = async (form) => {
    const payload = {
      username:  form.username,
      email:     form.email,
      role:      form.role,
      is_active: form.is_active,
      ...(form.password ? { password: form.password } : {}),
    };
    if (editingUser?.id) {
      await api.put(`/api/auth/users/${editingUser.id}`, payload);
    } else {
      await api.post("/api/auth/users", { ...payload, password: form.password });
    }
    setShowModal(false);
    setEditingUser(null);
    fetchUsers();
  };

  const toggleActive = async (user) => {
    await api.put(`/api/auth/users/${user.id}`, { ...user, is_active: !user.is_active });
    fetchUsers();
  };

  const deleteUser = async (user) => {
    if (user.id === currentUser?.id) { alert("Cannot delete your own account"); return; }
    if (!confirm(`Delete user "${user.username}"?`)) return;
    await api.delete(`/api/auth/users/${user.id}`);
    fetchUsers();
  };

  const filtered = users.filter(u =>
    u.username.toLowerCase().includes(search.toLowerCase()) ||
    u.email.toLowerCase().includes(search.toLowerCase())
  );

  if (currentUser?.role !== "admin") {
    return <div className="access-denied">Admin access required</div>;
  }

  return (
    <div className="users-page">
      <div className="page-header">
        <h1>User Management</h1>
        <button className="btn-primary" onClick={() => { setEditingUser(null); setShowModal(true); }}>
          + New User
        </button>
      </div>

      {error && <div className="page-error">{error}</div>}

      <div className="search-bar">
        <input
          placeholder="Search users…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <span className="user-count">{users.length} users</span>
      </div>

      <table className="users-table">
        <thead>
          <tr>
            <th>Username</th>
            <th>Email</th>
            <th>Role</th>
            <th>Status</th>
            <th>Last login</th>
            <th>Created</th>
            <th style={{width:120}}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr><td colSpan={7} style={{textAlign:"center",padding:32,color:"#666"}}>Loading…</td></tr>
          )}
          {!loading && filtered.map(u => (
            <tr key={u.id} className={u.is_active ? "" : "inactive"}>
              <td>
                <span className="username">{u.username}</span>
                {u.id === currentUser?.id && <span className="you-badge">you</span>}
              </td>
              <td className="email">{u.email}</td>
              <td>
                <span className="role-badge" style={{
                  background: ROLE_COLORS[u.role] + "22",
                  color: ROLE_COLORS[u.role],
                  border: `1px solid ${ROLE_COLORS[u.role]}44`,
                }}>
                  {u.role}
                </span>
              </td>
              <td>
                <span className={`status-dot ${u.is_active ? "active" : "inactive"}`} />
                {u.is_active ? "Active" : "Inactive"}
              </td>
              <td className="muted">{u.last_login ? fmtDate(u.last_login) : "Never"}</td>
              <td className="muted">{fmtDate(u.created_at)}</td>
              <td>
                <div className="row-actions">
                  <button className="act-btn edit" onClick={() => { setEditingUser(u); setShowModal(true); }}>Edit</button>
                  <button className="act-btn toggle" onClick={() => toggleActive(u)} disabled={u.id === currentUser?.id}>
                    {u.is_active ? "Disable" : "Enable"}
                  </button>
                  <button className="act-btn del" onClick={() => deleteUser(u)} disabled={u.id === currentUser?.id}>✕</button>
                </div>
              </td>
            </tr>
          ))}
          {!loading && filtered.length === 0 && (
            <tr><td colSpan={7} style={{textAlign:"center",padding:32,color:"#666"}}>No users found</td></tr>
          )}
        </tbody>
      </table>

      {showModal && (
        <UserModal
          user={editingUser}
          onSave={saveUser}
          onClose={() => { setShowModal(false); setEditingUser(null); }}
        />
      )}

      <style>{`
        .users-page { padding:24px; max-width:1100px; margin:0 auto; }
        .page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
        .page-header h1 { margin:0; font-size:22px; }
        .search-bar { display:flex; align-items:center; gap:12px; margin-bottom:16px; }
        .search-bar input { flex:1; max-width:320px; background:#1e2330; border:1px solid #2a2f3e; border-radius:6px; color:#ddd; padding:8px 12px; font-size:13px; outline:none; }
        .search-bar input:focus { border-color:#4a9eff; }
        .user-count { font-size:12px; color:#666; }
        .users-table { width:100%; border-collapse:collapse; font-size:13px; }
        .users-table th { text-align:left; padding:10px 12px; border-bottom:2px solid #2a2f3e; font-size:11px; color:#888; font-weight:500; text-transform:uppercase; letter-spacing:.4px; }
        .users-table td { padding:10px 12px; border-bottom:1px solid #1e2330; vertical-align:middle; }
        .users-table tr.inactive td { opacity:.5; }
        .users-table tr:hover td { background:#1a2035; }
        .username { font-weight:500; }
        .you-badge { background:#1a3a5c; color:#4a9eff; padding:1px 6px; border-radius:8px; font-size:10px; margin-left:6px; }
        .email { color:#888; font-size:12px; }
        .role-badge { padding:2px 10px; border-radius:10px; font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.4px; }
        .status-dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:6px; }
        .status-dot.active { background:#2ecc71; }
        .status-dot.inactive { background:#666; }
        .muted { color:#666; font-size:12px; }
        .row-actions { display:flex; gap:4px; }
        .act-btn { padding:3px 8px; border:none; border-radius:4px; font-size:11px; cursor:pointer; }
        .act-btn.edit   { background:#1a3a5c; color:#4a9eff; }
        .act-btn.toggle { background:#1a3a2a; color:#34d399; }
        .act-btn.del    { background:#3a1a1a; color:#e74c3c; }
        .act-btn:disabled { opacity:.3; cursor:default; }
        .access-denied { display:flex; align-items:center; justify-content:center; height:60vh; color:#888; font-size:16px; }
        .page-error { background:#2a1a1a; border:1px solid #5a2a2a; border-radius:6px; padding:10px 14px; color:#e74c3c; margin-bottom:16px; font-size:13px; }
        .modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,.7); display:flex; align-items:center; justify-content:center; z-index:1000; }
        .modal { background:#1a1f2e; border-radius:10px; padding:24px; width:420px; max-width:95vw; }
        .modal h3 { margin:0 0 20px; font-size:17px; }
        .modal label { display:block; font-size:12px; color:#888; margin:12px 0 4px; }
        .modal input, .modal select { width:100%; background:#111; border:1px solid #333; border-radius:5px; color:#fff; padding:8px 10px; font-size:13px; box-sizing:border-box; outline:none; }
        .modal input:focus, .modal select:focus { border-color:#4a9eff; }
        .modal-error { background:#2a1a1a; border:1px solid #5a2a2a; border-radius:5px; padding:8px 12px; color:#e74c3c; font-size:12px; margin-bottom:12px; }
        .modal-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:20px; }
        .btn-primary  { background:#4a9eff; color:#fff; border:none; border-radius:5px; padding:8px 16px; cursor:pointer; font-size:13px; font-weight:500; }
        .btn-secondary { background:#333; color:#ccc; border:none; border-radius:5px; padding:8px 16px; cursor:pointer; font-size:13px; }
      `}</style>
    </div>
  );
}

function fmtDate(s) {
  if (!s) return "—";
  return new Date(s).toLocaleDateString("en-US", { year:"numeric", month:"short", day:"numeric" });
}
