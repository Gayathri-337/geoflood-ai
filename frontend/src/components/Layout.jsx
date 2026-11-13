import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/authContext.js";

const ANALYST_ROLES = new Set(["analyst", "admin"]);

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="d-flex flex-column min-vh-100">
      <nav className="navbar navbar-dark bg-dark">
        <div className="container-fluid">
          <div className="d-flex align-items-center gap-4">
            <Link className="navbar-brand" to="/">
              GeoFlood AI
            </Link>
            <Link className="nav-link text-light p-0" to="/events">
                Events
            </Link>
            {ANALYST_ROLES.has(user.role) && (
              <Link className="nav-link text-light p-0" to="/upload">
                New analysis
              </Link>
            )}
          </div>
          <div className="d-flex align-items-center gap-3 text-light">
            <span>{user.full_name || user.username}</span>
            <span className="badge text-bg-secondary">{user.role}</span>
            <button type="button" className="btn btn-outline-light btn-sm" onClick={handleLogout}>
              Log out
            </button>
          </div>
        </div>
      </nav>

      <main className="container-fluid py-4 flex-grow-1">
        <Outlet />
      </main>

      <footer className="border-top py-2 text-center text-muted small">
        College project. Results are model estimates from Sentinel-1 radar, not official flood maps.
      </footer>
    </div>
  );
}