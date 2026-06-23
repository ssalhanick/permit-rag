import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import App from "./App.jsx";
import UploadPage from "./UploadPage.jsx";
import DocumentBrowserPage from "./DocumentBrowserPage.jsx";
import ProjectsPage from "./ProjectsPage.jsx";
import AuthPage from "./AuthPage.jsx";
import ProfilePage from "./ProfilePage.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import NotFoundPage from "./components/NotFoundPage.jsx";
import Nav from "./Nav.jsx";
import { AuthProvider } from "./context/AuthContext.jsx";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Nav />
        <Routes>
          <Route path="/" element={<App />} />
          <Route
            path="/documents"
            element={
              <ProtectedRoute>
                <DocumentBrowserPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/upload"
            element={
              <ProtectedRoute>
                <UploadPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projects"
            element={
              <ProtectedRoute>
                <ProjectsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <ProfilePage />
              </ProtectedRoute>
            }
          />
          <Route path="/auth" element={<AuthPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
