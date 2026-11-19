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

  it("renders \\[ \\] and \\( \\) maths with KaTeX but leaves prices and code alone", () => {
    const { container } = render(
      <MarkdownContent content={"So \\( t = 4 \\) s.\n\n\\[ t = \\sqrt{16} \\]\n\nThe ball costs $0.05 and the bat $1.05.\n\n```\nx = \"\\\\(raw\\\\)\"\n```"} />,
    );
    expect(container.querySelectorAll(".katex").length).toBe(2);
    expect(container.textContent).toContain("The ball costs $0.05 and the bat $1.05.");
    expect(container.querySelector("pre")?.textContent).toContain("\\\\(raw\\\\)");
  });

  it("renders links", () => {
    render(<MarkdownContent content={"[Corvus](https://example.com)"} />);
    const link = screen.getByRole("link", { name: "Corvus" });
    expect(link.getAttribute("href")).toBe("https://example.com");
  });
});
