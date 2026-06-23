import React from "react";
import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <main className="page" style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "calc(100vh - 120px)" }}>
      <section className="panel" style={{ maxWidth: "500px", textAlign: "center", padding: "40px 30px", borderRadius: "12px", border: "1px solid rgba(255, 255, 255, 0.08)", background: "rgba(30, 41, 59, 0.7)", backdropFilter: "blur(12px)", boxShadow: "0 8px 32px 0 rgba(0, 0, 0, 0.37)" }}>
        <h1 style={{ fontSize: "5rem", margin: "0 0 10px 0", color: "#3b82f6", fontWeight: "800", letterSpacing: "-0.05em", lineHeight: 1 }}>404</h1>
        <h2 style={{ fontSize: "1.75rem", color: "#f8fafc", marginBottom: "12px", fontWeight: "700" }}>Page Not Found</h2>
        <p className="muted" style={{ fontSize: "1rem", color: "#94a3b8", marginBottom: "28px", lineHeight: "1.6" }}>
          The page you are looking for doesn't exist or has been moved. Check the URL or click the button below to return to safety.
        </p>
        <Link to="/" className="primary-button" style={{ display: "inline-block", padding: "12px 28px", borderRadius: "8px", textDecoration: "none", fontWeight: "600", fontSize: "1rem", transition: "all 0.2s ease", background: "#2563eb", color: "#fff" }}>
          Back to Homepage
        </Link>
      </section>
    </main>
  );
}
