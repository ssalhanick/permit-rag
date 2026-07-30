import React, { createContext, useContext, useEffect, useState } from "react";
import { fetchContractorProfile } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";

const ContractorContext = createContext(null);

/**
 * Load the caller's own contractor profile for nested /contractor/* routes.
 */
export function ContractorProvider({ children }) {
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function reload() {
    setLoading(true);
    setError("");
    try {
      const res = await fetchContractorProfile();
      setProfile(res.data);
      return res.data;
    } catch (err) {
      setError(err.message || "Failed to load contractor profile.");
      return null;
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    if (!user) {
      return undefined;
    }
    (async () => {
      setLoading(true);
      setError("");
      try {
        const res = await fetchContractorProfile();
        if (active) {
          setProfile(res.data);
        }
      } catch (err) {
        if (active) {
          setError(err.message || "Failed to load contractor profile.");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [user]);

  const value = { profile, setProfile, loading, error, reload };
  return <ContractorContext.Provider value={value}>{children}</ContractorContext.Provider>;
}

export function useContractor() {
  const ctx = useContext(ContractorContext);
  if (!ctx) {
    throw new Error("useContractor must be used within ContractorProvider");
  }
  return ctx;
}
