import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthContext } from "../auth/authContext.js";
import { USER } from "../testUtils.js";
import Layout from "./Layout.jsx";

function renderLayout(role) {
  return render(
    <AuthContext.Provider value={{ user: { ...USER, role }, loading: false, login: vi.fn(), logout: vi.fn() }}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<div>home</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("navigation bar", () => {
  it("shows the events link to everyone", () => {
    renderLayout("viewer");
    expect(screen.getByRole("link", { name: "Events" })).toHaveAttribute("href", "/events");
    expect(screen.getByText("home")).toBeInTheDocument();
  });

  it("shows 'New analysis' only to analysts and admins", () => {
    const { unmount } = renderLayout("viewer");
    expect(screen.queryByRole("link", { name: "New analysis" })).toBeNull();
    unmount();
    renderLayout("analyst");
    expect(screen.getByRole("link", { name: "New analysis" })).toHaveAttribute("href", "/upload");
  });

  it("shows who is logged in and a log out button", () => {
    renderLayout("admin");
    expect(screen.getByText("Test Admin")).toBeInTheDocument();
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument();
  });
});
