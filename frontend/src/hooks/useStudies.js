// src/hooks/useStudies.js
import { useState, useEffect, useCallback } from "react";
import api from "../lib/api";

const DEFAULT_FILTERS = {
  patient_name: "",
  patient_id: "",
  accession: "",
  modality: "",
  date_from: "",
  date_to: "",
  status: "",
  partition: "",
};

export function useStudies(initialFilters = {}) {
  const [studies,    setStudies]    = useState([]);
  const [total,      setTotal]      = useState(0);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState(null);
  const [page,       setPage]       = useState(1);
  const [pageSize]                  = useState(50);
  const [filters,    setFilters]    = useState({ ...DEFAULT_FILTERS, ...initialFilters });
  const [sortBy,     setSortBy]     = useState("study_date");
  const [sortDir,    setSortDir]    = useState("desc");

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "")),
        skip:  (page - 1) * pageSize,
        limit: pageSize,
        sort_by:  sortBy,
        sort_dir: sortDir,
      };
      const { data } = await api.get("/api/studies", { params });
      // Handle both paginated {items, total} and plain array responses
      if (Array.isArray(data)) {
        setStudies(data);
        setTotal(data.length);
      } else {
        setStudies(data.items || []);
        setTotal(data.total || 0);
      }
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load studies");
    } finally {
      setLoading(false);
    }
  }, [filters, page, pageSize, sortBy, sortDir]);

  useEffect(() => { fetch(); }, [fetch]);

  const updateFilter = (key, value) => {
    setPage(1);
    setFilters(f => ({ ...f, [key]: value }));
  };

  const resetFilters = () => {
    setPage(1);
    setFilters({ ...DEFAULT_FILTERS });
  };

  const toggleSort = (col) => {
    if (sortBy === col) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortBy(col);
      setSortDir("desc");
    }
    setPage(1);
  };

  return {
    studies, total, loading, error,
    page, setPage, pageSize,
    filters, updateFilter, resetFilters,
    sortBy, sortDir, toggleSort,
    refresh: fetch,
  };
}
