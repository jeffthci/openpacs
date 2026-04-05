// src/lib/api.js
// Axios instance — automatically attaches JWT, handles 401 refresh
import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const api = axios.create({ baseURL: BASE_URL });

// ── Attach token on every request ─────────────────────────────────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── Handle 401 — redirect to login ────────────────────────────────
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("user");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;

// ── Typed helper wrappers ──────────────────────────────────────────

export const dicomweb = axios.create({ baseURL: BASE_URL });
dicomweb.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  // DICOMweb requests need CORS-safe headers
  config.headers["Accept"] = "application/dicom+json";
  return config;
});
