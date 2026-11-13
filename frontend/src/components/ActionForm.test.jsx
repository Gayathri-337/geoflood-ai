import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ActionForm from "./ActionForm.jsx";

const USER = { user_id: 7, username: "analyst" };
const PIN = { longitude: 93.7554, latitude: 26.5834 };

function renderForm(props = {}) {
  const handlers = {
    onPickingChange: vi.fn(), onClearPin: vi.fn(), onSubmit: vi.fn().mockResolvedValue(undefined), onClose: vi.fn(),
  };
  render(<ActionForm user={USER} pin={null} picking={false} {...handlers} {...props} />);
  return handlers;
}
const title = () => screen.getByLabelText(/^title$/i);
const save = () => screen.getByRole("button", { name: /save action/i });

describe("action form", () => {
  it("needs a title before anything is sent", async () => {
    const { onSubmit } = renderForm();
    await userEvent.setup().click(save());
    expect(screen.getByRole("alert")).toHaveTextContent("Give the action a title.");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("sends the trimmed text with the chosen type and priority", async () => {
    const { onSubmit } = renderForm();
    const user = userEvent.setup();
    await user.type(title(), "  Evacuate Village Alpha ");
    await user.selectOptions(screen.getByLabelText(/^type$/i), "rescue");
    await user.selectOptions(screen.getByLabelText(/^priority$/i), "critical");
    await user.type(screen.getByLabelText(/description/i), " Move now ");
    await user.click(save());

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0]).toEqual({
      title: "Evacuate Village Alpha", action_type: "rescue", priority: "critical", description: "Move now",
      location: null, assigned_to: null, due_at: null,
    });
  });

  it("assigns the action to the logged-in user when asked", async () => {
    const { onSubmit } = renderForm();
    const user = userEvent.setup();
    await user.type(title(), "Open the shelter");
    await user.click(screen.getByLabelText(/assign to me/i));
    await user.click(save());
    expect(onSubmit.mock.calls[0][0].assigned_to).toBe(7);
  });

  it("sends the due time as an exact moment", async () => {
    const { onSubmit } = renderForm();
    const user = userEvent.setup();
    await user.type(title(), "Open the shelter");
    fireEvent.change(screen.getByLabelText(/due/i), { target: { value: "2026-11-20T09:00" } });
    await user.click(save());
    expect(onSubmit.mock.calls[0][0].due_at).toBe(new Date("2026-11-20T09:00").toISOString());
  });

  it("shows the chosen pin, sends it, and lets the user clear it", async () => {
    const { onSubmit, onClearPin } = renderForm({ pin: PIN });
    const user = userEvent.setup();
    expect(screen.getByTestId("pin-text")).toHaveTextContent("Pin at 26.5834, 93.7554");
    await user.type(title(), "Close the bridge");
    await user.click(save());
    expect(onSubmit.mock.calls[0][0].location).toEqual(PIN);

    await user.click(screen.getByRole("button", { name: /clear pin/i }));
    expect(onClearPin).toHaveBeenCalledTimes(1);
  });

  it("shows 'No pin yet' without a pin, and no clear button", () => {
    renderForm();
    expect(screen.getByTestId("pin-text")).toHaveTextContent("No pin yet.");
    expect(screen.queryByRole("button", { name: /clear pin/i })).toBeNull();
  });

  it("switches picking on and off", async () => {
    const first = renderForm();
    await userEvent.setup().click(screen.getByRole("button", { name: /pick on map/i }));
    expect(first.onPickingChange).toHaveBeenCalledWith(true);
  });

  it("shows the button as pressed while picking, and stops picking when clicked again", async () => {
    const { onPickingChange } = renderForm({ picking: true });
    const button = screen.getByRole("button", { name: /stop picking/i });
    expect(button).toHaveAttribute("aria-pressed", "true");
    await userEvent.setup().click(button);
    expect(onPickingChange).toHaveBeenCalledWith(false);
  });

  it("shows the server's message and keeps what was typed when saving fails", async () => {
    renderForm({ onSubmit: vi.fn().mockRejectedValue(new Error("The person to assign does not exist or is disabled.")) });
    const user = userEvent.setup();
    await user.type(title(), "Open the shelter");
    await user.click(save());
    expect(await screen.findByRole("alert")).toHaveTextContent("does not exist or is disabled");
    expect(title()).toHaveValue("Open the shelter");
    expect(save()).toBeEnabled();
  });

  it("clears the form after a successful save", async () => {
    renderForm();
    const user = userEvent.setup();
    await user.type(title(), "Open the shelter");
    await user.click(save());
    await vi.waitFor(() => expect(title()).toHaveValue(""));
  });

  it("is disabled while saving, so one click sends one action", async () => {
    let finish;
    const onSubmit = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    renderForm({ onSubmit });
    const user = userEvent.setup();
    await user.type(title(), "Open the shelter");
    await user.click(save());

    const busy = await screen.findByRole("button", { name: /saving/i });
    expect(busy).toBeDisabled();
    await user.click(busy);
    expect(onSubmit).toHaveBeenCalledTimes(1);
    finish();
    expect(await screen.findByRole("button", { name: /save action/i })).toBeEnabled();
  });

  it("closes when asked", async () => {
    const { onClose } = renderForm();
    await userEvent.setup().click(screen.getByRole("button", { name: /^close$/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
