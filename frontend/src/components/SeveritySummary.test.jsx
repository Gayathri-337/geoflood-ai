import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SeveritySummary from "./SeveritySummary.jsx";

describe("severity summary", () => {
  it("shows every level with its count, and the analyses that are not classified", () => {
    render(<SeveritySummary counts={{ low: 1, moderate: 0, high: 2, severe: 3, not_classified: 4 }} />);
    const box = screen.getByTestId("severity-summary");
    expect(box).toHaveTextContent("Severe 3");
    expect(box).toHaveTextContent("High 2");
    expect(box).toHaveTextContent("Moderate 0");
    expect(box).toHaveTextContent("Low 1");
    expect(box).toHaveTextContent("Not classified yet: 4");
    expect(box).toHaveTextContent(/provisional/i);
    expect(screen.getByText("Severe 3")).toHaveClass("text-bg-dark");
  });

  it("treats missing numbers as 0", () => {
    render(<SeveritySummary counts={{ severe: 1 }} />);
    expect(screen.getByTestId("severity-summary")).toHaveTextContent("Low 0");
    expect(screen.getByTestId("severity-summary")).toHaveTextContent("Not classified yet: 0");
  });

  it("shows nothing when there are no counts", () => {
    const { container, rerender } = render(<SeveritySummary counts={undefined} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<SeveritySummary counts={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
