import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ConfirmationCard } from "./ConfirmationCard";
import { useCorvus } from "../state/store";
import type { RiskTier } from "../lib/api";

function showPrompt(risk: RiskTier, prompt: string) {
  useCorvus.setState({ pendingConfirmation: { name: "act", prompt, risk } });
  return render(<ConfirmationCard />);
}

describe("ConfirmationCard", () => {
  it("renders nothing when no action is awaiting an answer", () => {
    useCorvus.setState({ pendingConfirmation: null });
    const { container } = render(<ConfirmationCard />);
    expect(container.firstChild).toBeNull();
  });

  it("states the exact consequence rather than a generic prompt", () => {
    showPrompt("high", 'This will permanently delete "report.docx". Continue?');
    expect(screen.getByText(/permanently delete "report\.docx"/)).toBeTruthy();
    expect(screen.queryByText(/are you sure/i)).toBeNull();
  });

  it("reports the action's real risk tier, not always high", () => {
    showPrompt("medium", 'Create a new folder at "C:\\Users\\me\\Notes"?');
    expect(screen.getByText("medium risk")).toBeTruthy();
    expect(screen.queryByText("high risk")).toBeNull();
  });

  it("answers the pending confirmation and clears it", () => {
    showPrompt("high", "This will shut down your computer in 5 seconds. Continue?");
    fireEvent.click(screen.getByText("Cancel"));
    expect(useCorvus.getState().pendingConfirmation).toBeNull();
  });
});
