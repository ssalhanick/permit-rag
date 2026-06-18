import React, { createContext, useContext, useEffect, useState } from "react";
import { loginUser, logoutUser, registerUser } from "../api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Helper to parse JWT payload
  function parseJwt(token) {
    try {
      return JSON.parse(atob(token.split(".")[1]));
    } catch {
      return null;
    }
  }

  const checkUserSession = () => {
    const token = localStorage.getItem("access_token");
    if (token) {
      const payload = parseJwt(token);
      if (payload && payload.exp * 1000 > Date.now()) {
        setUser({
          id: payload.sub,
          role: payload.role,
          username: payload.username || "User",
        });
      } else {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        setUser(null);
      }
    } else {
      setUser(null);
    }
    setLoading(false);
  };

  useEffect(() => {
    checkUserSession();
    // Listen to changes in local storage (e.g. from other tabs or interceptors)
    window.addEventListener("storage", checkUserSession);
    return () => window.removeEventListener("storage", checkUserSession);
  }, []);

  const handleRegister = async (username, password, email, phone) => {
    const res = await registerUser({
      username,
      password,
      email,
      phone_number: phone || null,
    });
    checkUserSession();
    return res;
  };

  const handleLogin = async (identifier, password) => {
    const res = await loginUser({ identifier, password });
    checkUserSession();
    return res;
  };

  const handleLogout = async () => {
    await logoutUser();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login: handleLogin,
        register: handleRegister,
        logout: handleLogout,
        checkSession: checkUserSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
