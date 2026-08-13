import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

type MarkdownContentProps = Omit<
  ComponentProps<typeof ReactMarkdown>,
  "remarkPlugins" | "rehypePlugins"
>;

function MarkdownContent(props: MarkdownContentProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
      {...props}
    />
  );
}

export { MarkdownContent };
