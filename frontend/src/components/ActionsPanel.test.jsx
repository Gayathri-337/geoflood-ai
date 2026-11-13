import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ACTIONS } from "../eventFixtures.js";
import ActionsPanel from "./ActionsPanel.jsx";

const FILTERS = { status: "", priority: "" };

function renderPanel(props = {}) {
  const handlers = { onFilterChange: vi.fn(), onStatus: vi.fn(), onDelete: vi.fn() };
  render(<ActionsPanel actions={ACTIONS} filters={FILTERS} canEdit canDelete {...handlers} {...props} />);
  return handlers;
}
const item = (id) => within(screen.getByTestId(`action-${id}`));
const buttons = (id) => item(id).getAllByRole("button").map((b) => b.textContent);

describe("actions panel", () => {
  it("lists every action with its priority, status, type, assignee and pin", () => {
    renderPanel();
    expect(screen.getAllByTestId(/^action-/)).toHaveLength(3);
    expect(item(12).getByText("Evacuate the school")).toBeInTheDocument();
    expect(item(12).getByText("Critical")).toBeInTheDocument();
    expect(item(12).getByText("Planned")).toBeInTheDocument();
    expect(item(12).getByText(/Evacuation/)).toHaveTextContent("has a map pin");
    expect(item(11).getByText("In progress")).toBeInTheDocument();
    expect(item(11).getByText(/assigned to admin/)).toBeInTheDocument();
    expect(item(10).getByText(/Relief distribution/)).not.toHaveTextContent("has a map pin");
  });

  it("flags an open action whose due time has passed, but not a completed one", () => {
    renderPanel();
    expect(item(12).getByText("Overdue")).toBeInTheDocument();
    expect(item(11).queryByText("Overdue")).toBeNull();
    expect(item(10).queryByText("Overdue")).toBeNull(); // past due, but completed
  });

  it("tells the page when a filter changes", async () => {
    const { onFilterChange } = renderPanel();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText(/filter by status/i), "planned");
    expect(onFilterChange).toHaveBeenLastCalledWith({ status: "planned", priority: "" });
    await user.selectOptions(screen.getByLabelText(/filter by priority/i), "critical");
    expect(onFilterChange).toHaveBeenLastCalledWith({ status: "", priority: "critical" });
  });

  it("shows no buttons to someone who may not edit", () => {
    renderPanel({ canEdit: false, canDelete: false });
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("offers the right status buttons for each status, and reports a click", async () => {
    const { onStatus } = renderPanel();
    expect(buttons(12)).toEqual(["Start", "Complete", "Cancel action", "Delete"]);
    expect(buttons(11)).toEqual(["Complete", "Cancel action", "Delete"]);
    expect(buttons(10)).toEqual(["Reopen", "Delete"]);

    await userEvent.setup().click(item(12).getByRole("button", { name: "Start" }));
    expect(onStatus).toHaveBeenCalledWith(ACTIONS[0], "in_progress");
  });

  it("disables the buttons of the action that is being changed", () => {
    renderPanel({ busyId: 12 });
    for (const button of item(12).getAllByRole("button")) expect(button).toBeDisabled();
    for (const button of item(11).getAllByRole("button")) expect(button).toBeEnabled();
  });

  it("asks for a confirmation before deleting, and 'Keep' backs out", async () => {
    const { onDelete } = renderPanel();
    const user = userEvent.setup();

    await user.click(item(10).getByRole("button", { name: "Delete" }));
    expect(onDelete).not.toHaveBeenCalled();
    expect(buttons(10)).toEqual(["Reopen", "Delete permanently", "Keep"]);

    await user.click(item(10).getByRole("button", { name: "Keep" }));
    expect(buttons(10)).toEqual(["Reopen", "Delete"]);
    expect(onDelete).not.toHaveBeenCalled();

    await user.click(item(10).getByRole("button", { name: "Delete" }));
    await user.click(item(10).getByRole("button", { name: "Delete permanently" }));
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledWith(ACTIONS[2]);
  });

  it("does not offer deleting unless the user may delete", () => {
    renderPanel({ canDelete: false });
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    expect(buttons(12)).toEqual(["Start", "Complete", "Cancel action"]);
  });

  it("shows an error message and an empty list message", () => {
    const { rerender } = render(
      <ActionsPanel actions={ACTIONS} filters={FILTERS} canEdit canDelete onFilterChange={vi.fn()} onStatus={vi.fn()} onDelete={vi.fn()} error="This action needs the 'analyst' role or higher." />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("needs the 'analyst' role");
    rerender(<ActionsPanel actions={[]} filters={FILTERS} canEdit canDelete onFilterChange={vi.fn()} onStatus={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText("No actions match.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
