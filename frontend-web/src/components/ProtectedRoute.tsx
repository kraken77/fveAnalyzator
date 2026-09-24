import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({
  children,
  adminOnly = false,
  roles: allowedRoles,
}: {
  children: React.ReactNode;
  adminOnly?: boolean;
  roles?: string[];
}) {
  const { user, token, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-pulse text-slate-500 text-sm">Načítání...</div>
      </div>
    );
  }

  if (!token || !user) {
    return <Navigate to="/login" replace />;
  }

  const userRoles = user.roles && user.roles.length ? user.roles : [user.role];

  if (adminOnly && !userRoles.includes("admin")) {
    return <Navigate to="/projects" replace />;
  }
  if (allowedRoles && allowedRoles.length && !allowedRoles.some((r) => userRoles.includes(r))) {
    return <Navigate to="/projects" replace />;
  }

  return <>{children}</>;
}