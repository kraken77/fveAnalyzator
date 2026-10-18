import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";

import Login from "./pages/Login";
import Register from "./pages/Register";
import Projects from "./pages/Projects";
import ProjectDetail from "./pages/ProjectDetail";
import PublicPreview from "./pages/PublicPreview";
import Admin from "./pages/Admin";
import Dispecink from "./pages/Dispecink";
import Planovani from "./pages/Planovani";
import PipelineDetail from "./pages/PipelineDetail";
import Materialy from "./pages/Materialy";
import AdminPipeline from "./pages/AdminPipeline";
import FveAnalysisPage from "./pages/FveAnalysis";
import ProjectFveAnalysisPage from "./pages/ProjectFveAnalysis";
import ChangelogPage from "./pages/ChangelogPage";
import AboutPage from "./pages/AboutPage";

function ProtectedLayout({
  children,
  adminOnly = false,
  roles,
}: {
  children: React.ReactNode;
  adminOnly?: boolean;
  roles?: string[];
}) {
  return (
    <ProtectedRoute adminOnly={adminOnly} roles={roles}>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* public teaser - no Layout, own header */}
          <Route path="/p/:code" element={<PublicPreview />} />

          {/* auth */}
          <Route
            path="/login"
            element={
              <Layout>
                <Login />
              </Layout>
            }
          />
          <Route
            path="/register"
            element={
              <Layout>
                <Register />
              </Layout>
            }
          />

          {/* dispečink (interní uživatelé) */}
          <Route
            path="/dispecink"
            element={
              <ProtectedLayout roles={["admin", "antelon", "sales", "designer", "buyer", "warehouse", "subsidy", "connection", "electrician", "roofer", "inspector"]}>
                <Dispecink />
              </ProtectedLayout>
            }
          />

          {/* plánování montáže a elektro (interní uživatelé) */}
          <Route
            path="/planovani"
            element={
              <ProtectedLayout roles={["admin", "antelon", "sales", "designer", "buyer", "warehouse", "subsidy", "connection", "electrician", "roofer", "inspector"]}>
                <Planovani />
              </ProtectedLayout>
            }
          />

          {/* materiály */}
          <Route
            path="/materialy"
            element={
              <ProtectedLayout roles={["admin", "antelon", "buyer", "warehouse"]}>
                <Materialy />
              </ProtectedLayout>
            }
          />
          <Route
            path="/projects/:id/materialy"
            element={
              <ProtectedLayout>
                <Materialy />
              </ProtectedLayout>
            }
          />

          {/* pipeline detail */}
          <Route
            path="/projects/:id/pipeline"
            element={
              <ProtectedLayout>
                <PipelineDetail />
              </ProtectedLayout>
            }
          />

          {/* fveAnalysis — standalone i uvnitř zakázky. Bez `roles`:
              dostupné každému přihlášenému, tedy i zákazníkovi. */}
          <Route
            path="/fve-analysis"
            element={
              <ProtectedLayout>
                <FveAnalysisPage />
              </ProtectedLayout>
            }
          />
          <Route
            path="/projects/:id/fve-analysis"
            element={
              <ProtectedLayout>
                <ProjectFveAnalysisPage />
              </ProtectedLayout>
            }
          />

          {/* classic */}
          <Route
            path="/projects"
            element={
              <ProtectedLayout>
                <Projects />
              </ProtectedLayout>
            }
          />
          <Route
            path="/projects/:id"
            element={
              <ProtectedLayout>
                <ProjectDetail />
              </ProtectedLayout>
            }
          />
          <Route
            path="/admin"
            element={
              <ProtectedLayout adminOnly>
                <Admin />
              </ProtectedLayout>
            }
          />
          <Route
            path="/admin/pipeline"
            element={
              <ProtectedLayout adminOnly>
                <AdminPipeline />
              </ProtectedLayout>
            }
          />

          {/* info — veřejné (i bez loginu), položky v user menu */}
          <Route
            path="/changelog"
            element={
              <Layout>
                <ChangelogPage />
              </Layout>
            }
          />
          <Route
            path="/o-programu"
            element={
              <Layout>
                <AboutPage />
              </Layout>
            }
          />

          <Route path="/" element={<Navigate to="/dispecink" replace />} />
          <Route path="*" element={<Navigate to="/dispecink" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}