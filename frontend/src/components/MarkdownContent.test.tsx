import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarkdownContent } from "./MarkdownContent";

describe("MarkdownContent", () => {
  it("renders GFM tables", () => {
    render(<MarkdownContent content={"| a | b |\n|---|---|\n| 1 | 2 |"} />);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("1")).toBeTruthy();
  });

  it("renders fenced code blocks with a copy button and language label", () => {
    render(<MarkdownContent content={'```python\nprint("hi")\n```'} />);
    expect(screen.getByRole("button", { name: "Copy code" })).toBeTruthy();
    expect(screen.getByText("python")).toBeTruthy();
  });

  it("renders inline code without the copy chrome", () => {
    render(<MarkdownContent content={"use `npm run dev` here"} />);
    expect(screen.getByText("npm run dev")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Copy code" })).toBeNull();
  });

  it("renders links", () => {
    render(<MarkdownContent content={"[Corvus](https://example.com)"} />);
    const link = screen.getByRole("link", { name: "Corvus" });
    expect(link.getAttribute("href")).toBe("https://example.com");
  });
});
