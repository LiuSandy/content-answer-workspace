import type { ComponentProps } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

type MarkdownContentProps = Omit<
  ComponentProps<typeof ReactMarkdown>,
  "remarkPlugins" | "rehypePlugins"
>;

const markdownSanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [["className", /^language-./, "math-inline", "math-display"]],
    td: [...(defaultSchema.attributes?.td || []), "align", "colSpan", "rowSpan"],
    th: [...(defaultSchema.attributes?.th || []), "align", "colSpan", "rowSpan"],
  },
};

function classes(...values: Array<string | undefined>) {
  return values.filter(Boolean).join(" ");
}

const defaultComponents: Components = {
  pre: ({ node, className, ...props }) => (
    <pre
      className={classes(
        "my-4 max-w-full overflow-x-auto rounded-lg border border-slate-200 bg-slate-950 p-4 text-[0.8rem] leading-6 text-slate-100 shadow-sm",
        "dark:border-slate-700 dark:bg-slate-950",
        "[&_code]:border-0 [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-inherit",
        className,
      )}
      {...props}
    />
  ),
  code: ({ node, className, ...props }) => (
    <code
      className={classes(
        "rounded border border-slate-200 bg-slate-100 px-1.5 py-0.5 font-mono text-[0.88em] text-slate-800",
        "dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100",
        className,
      )}
      {...props}
    />
  ),
  table: ({ node, className, ...props }) => (
    <div className="my-4 max-w-full overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
      <table
        className={classes(
          "w-full min-w-max border-collapse text-left text-xs",
          "[&_tr:first-child_td]:bg-slate-100 [&_tr:first-child_td]:font-semibold",
          "dark:[&_tr:first-child_td]:bg-slate-800",
          className,
        )}
        {...props}
      />
    </div>
  ),
  thead: ({ node, className, ...props }) => (
    <thead className={classes("bg-slate-100 dark:bg-slate-800", className)} {...props} />
  ),
  th: ({ node, className, ...props }) => (
    <th
      className={classes(
        "border-b border-r border-slate-200 px-3 py-2 font-semibold last:border-r-0 dark:border-slate-700",
        className,
      )}
      {...props}
    />
  ),
  td: ({ node, className, ...props }) => (
    <td
      className={classes(
        "border-b border-r border-slate-200 px-3 py-2 align-top last:border-r-0 dark:border-slate-700",
        className,
      )}
      {...props}
    />
  ),
};

function MarkdownContent({ components, ...props }: MarkdownContentProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[
        rehypeRaw,
        [rehypeSanitize, markdownSanitizeSchema],
        [rehypeKatex, { strict: false, throwOnError: false }],
      ]}
      components={{ ...defaultComponents, ...components }}
      {...props}
    />
  );
}

export { MarkdownContent };
