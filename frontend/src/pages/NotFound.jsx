import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="container py-5 text-center">
      <h1 className="h3">Page not found</h1>
      <p className="text-muted">There is nothing at this address.</p>
      <Link to="/">Back to the dashboard</Link>
    </div>
  );
}
