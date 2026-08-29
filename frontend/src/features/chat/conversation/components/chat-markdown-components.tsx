import { cn } from "@/lib/utils";

/** Shared Markdown renderer definitions for user, history, and streaming messages. */
export function getChatMarkdownComponents(isUser: boolean) {
  return {
    h1: ({ node, ...props }: any) => (
      <h1
        className={cn(
          "text-lg font-bold mt-4 mb-2 border-b pb-1",
          isUser
            ? "text-primary-foreground border-primary-foreground/20"
            : "text-foreground border-border/40",
        )}
        {...props}
      />
    ),
    h2: ({ node, ...props }: any) => (
      <h2
        className={cn(
          "text-base font-bold mt-3.5 mb-1.5",
          isUser ? "text-primary-foreground/90" : "text-foreground",
        )}
        {...props}
      />
    ),
    h3: ({ node, ...props }: any) => (
      <h3
        className={cn(
          "text-sm font-bold mt-3 mb-1",
          isUser ? "text-primary-foreground/85" : "text-foreground/90",
        )}
        {...props}
      />
    ),
    p: ({ node, ...props }: any) => (
      <p className="text-sm leading-relaxed mb-2 last:mb-0" {...props} />
    ),
    ul: ({ node, ...props }: any) => (
      <ul className="list-disc pl-5 mb-3 space-y-1 text-sm" {...props} />
    ),
    ol: ({ node, ...props }: any) => (
      <ol className="list-decimal pl-5 mb-3 space-y-1 text-sm" {...props} />
    ),
    li: ({ node, ...props }: any) => <li className="text-sm leading-relaxed" {...props} />,
    blockquote: ({ node, ...props }: any) => (
      <blockquote
        className={cn(
          "border-l-4 pl-3 my-2 italic",
          isUser
            ? "border-primary-foreground/30 text-primary-foreground/75"
            : "border-muted-foreground/30 text-muted-foreground",
        )}
        {...props}
      />
    ),
    code: ({ node, inline, className, children, ...props }: any) =>
      !inline ? (
        <pre className="bg-muted/80 text-foreground p-3.5 rounded-xl my-2 overflow-x-auto text-xs font-mono border border-border/30 max-w-full">
          <code className={className} {...props}>
            {children}
          </code>
        </pre>
      ) : (
        <code
          className={cn(
            "px-1 py-0.5 rounded text-xs font-mono border",
            isUser
              ? "bg-primary-foreground/10 text-primary-foreground border-primary-foreground/20"
              : "bg-muted text-foreground border-border/30",
          )}
          {...props}
        >
          {children}
        </code>
      ),
    table: ({ node, ...props }: any) => (
      <div className="my-3 overflow-x-auto rounded-lg border border-border/30 max-w-full">
        <table className="min-w-full divide-y divide-border/30 text-xs" {...props} />
      </div>
    ),
    thead: ({ node, ...props }: any) => <thead className="bg-muted/40 font-semibold" {...props} />,
    tbody: ({ node, ...props }: any) => <tbody className="divide-y divide-border/20" {...props} />,
    tr: ({ node, ...props }: any) => <tr className="hover:bg-muted/5" {...props} />,
    th: ({ node, ...props }: any) => (
      <th className="px-3 py-2 text-left font-semibold text-foreground/80" {...props} />
    ),
    td: ({ node, ...props }: any) => <td className="px-3 py-2 text-foreground/75" {...props} />,
    a: ({ node, ...props }: any) => (
      <a
        className={cn(
          "hover:underline break-all font-medium",
          isUser ? "text-primary-foreground" : "text-blue-500",
        )}
        target="_blank"
        rel="noreferrer"
        {...props}
      />
    ),
  };
}
