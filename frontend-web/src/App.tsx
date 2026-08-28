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

function ProtectedLayout({ children, adminOnly = false }: { children: React.ReactNode; adminOnly?: boolean }) {
  return (
    <ProtectedRoute adminOnly={adminOnly}>
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

          {/* protected */}
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

          <Route path="/" element={<Navigate to="/projects" replace />} />
          <Route path="*" element={<Navigate to="/projects" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
