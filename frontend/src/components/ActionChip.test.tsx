import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ActionChip } from "./ActionChip";
import type { ActionEvent } from "../state/store";

function chip(overrides: Partial<ActionEvent> = {}) {
  const action: ActionEvent = {
    name: "delete_item",
    arguments: { path: "report.docx" },
    risk: "high",
    category: "files",
    status: "ok",
    ...overrides,
  };
  return render(<ActionChip action={action} />);
}

describe("ActionChip", () => {
  it("shows the action name, risk, and arguments", () => {
    chip();
    expect(screen.getByText("delete_item")).toBeTruthy();
    expect(screen.getByText("high")).toBeTruthy();
    expect(screen.getByText(/report\.docx/)).toBeTruthy();
  });

  it("surfaces failure messages", () => {
    chip({ status: "failed", message: "file not found" });
    expect(screen.getByText(/file not found/)).toBeTruthy();
  });

  it("marks declined actions", () => {
    chip({ status: "declined", message: "Cancelled" });
    expect(screen.getByText(/Cancelled/)).toBeTruthy();
  });
});
