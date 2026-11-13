import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import AnalysisPage from "./pages/AnalysisPage.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import EventPage from "./pages/EventPage.jsx";
import EventsPage from "./pages/EventsPage.jsx";
import Login from "./pages/Login.jsx";
import NotFound from "./pages/NotFound.jsx";
import UploadPage from "./pages/UploadPage.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="analyses/:analysisId" element={<AnalysisPage />} />
          <Route path="events" element={<EventsPage />} />
          <Route path="events/:eventId" element={<EventPage />} />
          <Route path="upload" element={<UploadPage />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}