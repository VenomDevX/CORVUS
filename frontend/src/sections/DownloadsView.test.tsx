import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DownloadsView } from "./DownloadsView";
import { useCorvus } from "../state/store";
import { api } from "../lib/api";

describe("DownloadsView", () => {
  beforeEach(() => {
    useCorvus.setState({ backendOnline: true });
  });

  it("shows an empty state when nothing has been downloaded", async () => {
    vi.spyOn(api, "downloads").mockResolvedValue([]);
    vi.spyOn(api, "browserStatus").mockResolvedValue({ available: true, open: false });
    render(<DownloadsView />);
    await waitFor(() => expect(screen.getByText(/Nothing downloaded yet/)).toBeTruthy());
  });

  it("lists downloaded files with their source", async () => {
    vi.spyOn(api, "downloads").mockResolvedValue([
      { filename: "report.pdf", path: "C:/x/report.pdf", url: "https://site/report.pdf", created_at: "2026-07-15T10:00:00" },
    ]);
    vi.spyOn(api, "browserStatus").mockResolvedValue({ available: true, open: true });
    render(<DownloadsView />);
    await waitFor(() => expect(screen.getByText("report.pdf")).toBeTruthy());
    expect(screen.getByText(/site\/report\.pdf/)).toBeTruthy();
    expect(screen.getByText(/session active/)).toBeTruthy();
  });
});
