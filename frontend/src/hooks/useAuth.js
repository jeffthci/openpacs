// src/hooks/useAuth.js
import { useState, useEffect, createContext, useContext } from "react";
import api from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(() => {
    try { return JSON.parse(localStorage.getItem("user")); } catch { return null; }
  });
  const [loading, setLoading] = useState(false);

  const login = async (username, password) => {
    setLoading(true);
    try {
      const { data } = await api.post("/api/auth/token",
        new URLSearchParams({ username, password }),
        { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
      );
      localStorage.setItem("access_token", data.access_token);
      const me = await api.get("/api/auth/me");
      localStorage.setItem("user", JSON.stringify(me.data));
      setUser(me.data);
      return me.data;
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    setUser(null);
    window.location.href = "/login";
  };

  const refreshUser = async () => {
    try {
      const me = await api.get("/api/auth/me");
      localStorage.setItem("user", JSON.stringify(me.data));
      setUser(me.data);
    } catch { logout(); }
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, loading, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
