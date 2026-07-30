import React, { useEffect } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import App from "./App.jsx";
import DashboardPage from "./DashboardPage.jsx";
import TasksPage from "./TasksPage.jsx";
import QueryPage from "./QueryPage.jsx";
import DebugQueryPage from "./DebugQueryPage.jsx";
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
import ProfileRoomScansPage from "./profile/pages/ProfileRoomScansPage.jsx";
import RoomDesignPage from "./profile/pages/RoomDesignPage.jsx";
import ProjectLayout from "./projects/ProjectLayout.jsx";
import { ProjectProvider } from "./projects/ProjectContext.jsx";
import ProjectDashboardPage from "./projects/pages/ProjectDashboardPage.jsx";
import ProjectScansPage from "./projects/pages/ProjectScansPage.jsx";
import ProjectQueriesPage from "./projects/pages/ProjectQueriesPage.jsx";
import ProjectDocumentsPage from "./projects/pages/ProjectDocumentsPage.jsx";
import ProjectMembersPage from "./projects/pages/ProjectMembersPage.jsx";
import ProjectSettingsPage from "./projects/pages/ProjectSettingsPage.jsx";
import ProjectPetitionPage from "./projects/pages/ProjectPetitionPage.jsx";
import ProjectTrashPage from "./projects/pages/ProjectTrashPage.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import SuperadminRoute from "./admin/SuperadminRoute.jsx";
import AgentDashboardPage from "./admin/AgentDashboardPage.jsx";
import NotFoundPage from "./components/NotFoundPage.jsx";
import OfflineBanner from "./components/OfflineBanner.jsx";
import BiometricGate from "./components/BiometricGate.jsx";
import Nav from "./Nav.jsx";
import { AuthProvider } from "./context/AuthContext.jsx";
import { ThemeProvider } from "./context/ThemeContext.jsx";
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
      <ThemeProvider>
        <AuthProvider>
          <MobileBootstrap />
          <OfflineBanner />
          <BiometricGate>
            <Nav />
            <Routes>
          <Route path="/" element={<App />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/tasks"
            element={
              <ProtectedRoute>
                <TasksPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/query"
            element={
              <ProtectedRoute>
                <QueryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/debug-query"
            element={
              <ProtectedRoute>
                <DebugQueryPage />
              </ProtectedRoute>
            }
          />
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
            path="/projects/:projectId"
            element={
              <ProtectedRoute>
                <ProjectProvider>
                  <ProjectLayout />
                </ProjectProvider>
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route path="dashboard" element={<ProjectDashboardPage />} />
            <Route path="scans" element={<ProjectScansPage />} />
            <Route path="scans/:scanId/design" element={<RoomDesignPage />} />
            <Route path="queries" element={<ProjectQueriesPage />} />
            <Route path="documents" element={<ProjectDocumentsPage />} />
            <Route path="members" element={<ProjectMembersPage />} />
            <Route path="settings" element={<ProjectSettingsPage />} />
            <Route path="petition" element={<ProjectPetitionPage />} />
          </Route>
          <Route
            path="/projects"
            element={
              <ProtectedRoute>
                <ProjectsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projects/trash"
            element={
              <ProtectedRoute>
                <ProjectTrashPage />
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
            <Route path="room-scans" element={<ProfileRoomScansPage />} />
            <Route path="room-scans/:scanId/design" element={<RoomDesignPage libraryMode />} />
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
          <Route
            path="/admin/agents"
            element={
              <SuperadminRoute>
                <AgentDashboardPage />
              </SuperadminRoute>
            }
          />
          <Route path="/auth" element={<AuthPage />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </BiometricGate>
      </AuthProvider>
    </ThemeProvider>
  </BrowserRouter>
</React.StrictMode>,
);
