// src/pages/Login.jsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function Login() {
  const { login }              = useAuth();
  const navigate               = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState(null);
  const [loading,  setLoading]  = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Login failed — check credentials");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <div className="logo-icon">✦</div>
          <div className="logo-text">
            <span className="logo-main">OpenPACS</span>
            <span className="logo-sub">Medical Imaging Server</span>
          </div>
        </div>

        <form onSubmit={submit}>
          {error && <div className="login-error">{error}</div>}

          <div className="field">
            <label>Username</label>
            <input
              autoFocus
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="username"
              autoComplete="username"
              required
            />
          </div>

          <div className="field">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="password"
              autoComplete="current-password"
              required
            />
          </div>

          <button type="submit" className="login-btn" disabled={loading}>
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>

        <p className="login-hint">Default: admin / admin — change after first login</p>
      </div>

      <style>{`
        .login-page {
          height: 100vh; display: flex; align-items: center; justify-content: center;
          background: #0d1117;
        }
        .login-card {
          background: #161b27; border: 1px solid #2a2f3e;
          border-radius: 12px; padding: 40px; width: 360px;
        }
        .login-logo { display: flex; align-items: center; gap: 14px; margin-bottom: 32px; }
        .logo-icon { font-size: 28px; color: #4a9eff; }
        .logo-text { display: flex; flex-direction: column; }
        .logo-main { font-size: 20px; font-weight: 700; color: #e8eaf0; letter-spacing: -.3px; }
        .logo-sub  { font-size: 11px; color: #666; margin-top: 1px; }
        .field { margin-bottom: 16px; }
        .field label { display: block; font-size: 12px; color: #888; margin-bottom: 6px; font-weight: 500; }
        .field input {
          width: 100%; background: #0d1117; border: 1px solid #2a2f3e;
          border-radius: 6px; color: #e8eaf0; padding: 10px 12px;
          font-size: 14px; box-sizing: border-box; outline: none;
          transition: border-color .2s;
        }
        .field input:focus { border-color: #4a9eff; }
        .login-btn {
          width: 100%; background: #4a9eff; color: #fff; border: none;
          border-radius: 6px; padding: 11px; font-size: 14px; font-weight: 600;
          cursor: pointer; margin-top: 8px; transition: background .2s;
        }
        .login-btn:hover:not(:disabled) { background: #3a8eef; }
        .login-btn:disabled { opacity: .6; cursor: default; }
        .login-error {
          background: #2a1818; border: 1px solid #5a2828; border-radius: 6px;
          padding: 10px 12px; color: #e74c3c; font-size: 13px; margin-bottom: 16px;
        }
        .login-hint { text-align: center; font-size: 11px; color: #444; margin-top: 20px; margin-bottom: 0; }
      `}</style>
    </div>
  );
}
