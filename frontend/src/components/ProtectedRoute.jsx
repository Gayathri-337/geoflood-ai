import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/authContext.js";

/** Shows the pages inside it only to a logged-in user; everyone else is sent to the login page. */
export default function ProtectedRoute() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="container py-5 text-center text-muted">Restoring your session…</div>;
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}
