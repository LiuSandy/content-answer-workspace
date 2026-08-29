import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";

import { MarkdownContent } from "./markdown-content";

test("renders inline and block LaTeX with KaTeX", () => {
  const html = renderToStaticMarkup(
    <MarkdownContent>
      {"行内公式 $a \\equiv b \\pmod n$\n\n$$\nx^2 + y^2 = z^2\n$$"}
    </MarkdownContent>,
  );

  expect(html.includes('class="katex"')).toEqual(true);
  expect(html.includes('class="katex-display"')).toEqual(true);
  expect(html.includes("$a")).toEqual(false);
});

test("renders fenced code and sanitized HTML tables", () => {
  const html = renderToStaticMarkup(
    <MarkdownContent>
      {
        '```python\nprint(\'hello\')\n```\n\n<table onclick="bad()"><tr><td rowspan="2">名称</td><td>值</td></tr><tr><td>1</td></tr></table><script>bad()</script>'
      }
    </MarkdownContent>,
  );

  expect(html.includes("language-python")).toEqual(true);
  expect(html.includes("bg-slate-950")).toEqual(true);
  expect(html.includes("<table")).toEqual(true);
  expect(html.includes('rowSpan="2"')).toEqual(true);
  expect(html.includes("onclick")).toEqual(false);
  expect(html.includes("<script")).toEqual(false);
});
