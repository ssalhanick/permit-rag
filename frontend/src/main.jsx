import React, { useEffect } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import App from "./App.jsx";
import UploadPage from "./UploadPage.jsx";
import DocumentBrowserPage from "./DocumentBrowserPage.jsx";
import ProjectsPage from "./ProjectsPage.jsx";
import ProjectKickoffPage from "./ProjectKickoffPage.jsx";
import AuthPage from "./AuthPage.jsx";
import AuthCallback from "./AuthCallback.jsx";
import ProfilePage from "./ProfilePage.jsx";
import ProfileDashboardPage from "./profile/pages/ProfileDashboardPage.jsx";
import ProfileHistoryPage from "./profile/pages/ProfileHistoryPage.jsx";
import ProfileDocumentsPage from "./profile/pages/ProfileDocumentsPage.jsx";
import ProfileAccountPage from "./profile/pages/ProfileAccountPage.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import NotFoundPage from "./components/NotFoundPage.jsx";
import OfflineBanner from "./components/OfflineBanner.jsx";
import BiometricGate from "./components/BiometricGate.jsx";
import Nav from "./Nav.jsx";
import { AuthProvider } from "./context/AuthContext.jsx";
import { initPushNotifications } from "./services/pushNotifications.js";
import { isNativePlatform } from "./platform.js";
import "./styles.css";

function MobileBootstrap() {
  useEffect(() => {
    if (!isNativePlatform()) {
      return undefined;
    }
    document.body.classList.add("native-app");
    initPushNotifications();
    return () => {
      document.body.classList.remove("native-app");
    };
  }, []);
  return null;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <MobileBootstrap />
        <OfflineBanner />
        <BiometricGate>
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
          >
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route path="dashboard" element={<ProfileDashboardPage />} />
            <Route path="history" element={<ProfileHistoryPage />} />
            <Route path="documents" element={<ProfileDocumentsPage />} />
            <Route path="account" element={<ProfileAccountPage />} />
          </Route>
          <Route
            path="/kickoff"
            element={
              <ProtectedRoute>
                <ProjectKickoffPage />
              </ProtectedRoute>
            }
          />
          <Route path="/auth" element={<AuthPage />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </BiometricGate>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
