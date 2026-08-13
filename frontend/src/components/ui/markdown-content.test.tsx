import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";

import { MarkdownContent } from "./markdown-content";

test("renders inline and block LaTeX with KaTeX", () => {
  const html = renderToStaticMarkup(
    <MarkdownContent>{"行内公式 $a \\equiv b \\pmod n$\n\n$$\nx^2 + y^2 = z^2\n$$"}</MarkdownContent>,
  );

  expect(html.includes('class="katex"')).toEqual(true);
  expect(html.includes('class="katex-display"')).toEqual(true);
  expect(html.includes("$a")).toEqual(false);
});
