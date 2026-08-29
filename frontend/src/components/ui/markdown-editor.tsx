import { useState } from "react";
import { type Components } from "react-markdown";

import { cn } from "@/lib/utils";
import { MarkdownContent } from "@/components/ui/markdown-content";

type MarkdownEditorProps = {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  placeholder?: string;
  readOnly?: boolean;
};

const markdownComponents: Components = {
  p: ({ node, ...props }) => <p className="my-3 leading-relaxed first:mt-0 last:mb-0" {...props} />,
  h1: ({ node, ...props }) => (
    <h1 className="mb-3 mt-5 text-xl font-semibold leading-snug first:mt-0" {...props} />
  ),
  h2: ({ node, ...props }) => (
    <h2 className="mb-2.5 mt-5 text-base font-semibold leading-snug first:mt-0" {...props} />
  ),
  h3: ({ node, ...props }) => (
    <h3 className="mb-2 mt-4 text-sm font-semibold leading-snug first:mt-0" {...props} />
  ),
  h4: ({ node, ...props }) => (
    <h4 className="mb-1.5 mt-3 text-sm font-semibold leading-snug first:mt-0" {...props} />
  ),
  ul: ({ node, ...props }) => <ul className="my-3 list-disc space-y-1.5 pl-5" {...props} />,
  ol: ({ node, ...props }) => <ol className="my-3 list-decimal space-y-1.5 pl-5" {...props} />,
  li: ({ node, ...props }) => <li className="leading-relaxed" {...props} />,
  a: ({ node, ...props }) => (
    <a
      className="text-blue-600 underline underline-offset-2 hover:text-blue-700"
      target="_blank"
      rel="noreferrer"
      {...props}
    />
  ),
  blockquote: ({ node, ...props }) => (
    <blockquote className="my-3 border-l-2 border-blue-200 pl-3 text-slate-600" {...props} />
  ),
  hr: ({ node, ...props }) => <hr className="my-4 border-slate-200" {...props} />,
  code: ({ node, ...props }) => (
    <code className="rounded bg-slate-100 px-1 py-0.5 text-[0.86em] text-slate-800" {...props} />
  ),
  pre: ({ node, ...props }) => (
    <pre
      className="my-3 overflow-x-auto rounded-md bg-slate-100 p-3 text-xs leading-relaxed text-slate-800 [&_code]:bg-transparent [&_code]:p-0"
      {...props}
    />
  ),
  table: ({ node, ...props }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-xs" {...props} />
    </div>
  ),
  thead: ({ node, ...props }) => <thead className="bg-slate-50" {...props} />,
  th: ({ node, ...props }) => (
    <th
      className="whitespace-nowrap border border-slate-200 px-3 py-2 text-left font-semibold"
      {...props}
    />
  ),
  td: ({ node, ...props }) => (
    <td className="border border-slate-200 px-3 py-2 align-top" {...props} />
  ),
};

function MarkdownEditor({
  value,
  onChange,
  className,
  placeholder,
  readOnly = false,
}: MarkdownEditorProps) {
  const [mode, setMode] = useState<"preview" | "source">(value.trim() ? "preview" : "source");

  return (
    <div className={cn("markdown-editor-shell", className)}>
      <div className="markdown-editor-toolbar">
        <button
          type="button"
          className={cn("markdown-editor-mode-button", mode === "preview" && "is-active")}
          onClick={() => setMode("preview")}
        >
          预览
        </button>
        <button
          type="button"
          className={cn("markdown-editor-mode-button", mode === "source" && "is-active")}
          onClick={() => setMode("source")}
        >
          源码
        </button>
      </div>

      {mode === "preview" ? (
        <div className="markdown-editor__content">
          {value.trim() ? (
            <MarkdownContent components={markdownComponents}>{value}</MarkdownContent>
          ) : (
            <p className="m-0 text-slate-400">{placeholder}</p>
          )}
        </div>
      ) : (
        <textarea
          className="markdown-editor__source"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          readOnly={readOnly}
        />
      )}
    </div>
  );
}

export { MarkdownEditor };
