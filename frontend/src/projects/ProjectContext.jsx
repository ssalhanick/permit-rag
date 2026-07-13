import React, { createContext, useContext, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { fetchProject, fetchProjectMembers } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";

const ProjectContext = createContext(null);

/**
 * Load project + membership for nested project routes.
 */
export function ProjectProvider({ children }) {
  const { projectId } = useParams();
  const { user } = useAuth();
  const [project, setProject] = useState(null);
  const [role, setRole] = useState("viewer");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    (async () => {
      if (!projectId || !user) {
        return;
      }
      setLoading(true);
      setError("");
      try {
        const [projRes, membersRes] = await Promise.all([
          fetchProject(projectId),
          fetchProjectMembers(projectId),
        ]);
        if (!active) {
          return;
        }
        setProject(projRes.data);
        const me = (membersRes.data || []).find((m) => m.user_id === user.id);
        if (me) {
          setRole(me.role);
        } else if (projRes.data?.owner_user_id === user.id) {
          setRole("owner");
        }
      } catch (err) {
        if (active) {
          setError(err.message || "Failed to load project.");
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
  }, [projectId, user]);

  const value = {
    project,
    setProject,
    role,
    canEdit: role === "owner" || role === "editor",
    loading,
    error,
    projectId,
  };

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

/**
 * @returns {object}
 */
export function useProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx) {
    throw new Error("useProject must be used within ProjectProvider");
  }
  return ctx;
}
