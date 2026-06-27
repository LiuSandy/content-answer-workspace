import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

/**
 * 聊天消息的只读 Markdown 渲染组件。
 * 单独定义是因为聊天气泡里的 ReactMarkdown 默认无任何样式（Tailwind preflight 重置了表格/列表/标题），
 * 这里用 components 把每类元素补齐样式，并把表格包进横向滚动容器，避免宽表在窄气泡里被压垮。
 * 抽成独立组件后，普通回答气泡与流式气泡共用同一套渲染，不重复样式定义。
 */

// 每类 Markdown 元素的样式映射；集中在此，便于统一调整聊天内的排版
const components: Components = {
  p: ({ node, ...props }) => <p className="my-3 leading-relaxed first:mt-0 last:mb-0" {...props} />,
  h1: ({ node, ...props }) => <h1 className="mb-2 mt-4 text-base font-semibold first:mt-0" {...props} />,
  h2: ({ node, ...props }) => <h2 className="mb-2 mt-4 text-sm font-semibold first:mt-0" {...props} />,
  h3: ({ node, ...props }) => <h3 className="mb-1.5 mt-3 text-sm font-semibold first:mt-0" {...props} />,
  ul: ({ node, ...props }) => <ul className="my-3 list-disc space-y-2 pl-5" {...props} />,
  ol: ({ node, ...props }) => <ol className="my-3 list-decimal space-y-2 pl-5" {...props} />,
  li: ({ node, ...props }) => <li className="leading-relaxed" {...props} />,
  a: ({ node, ...props }) => (
    <a
      className="text-primary underline underline-offset-2 hover:opacity-80"
      target="_blank"
      rel="noreferrer"
      {...props}
    />
  ),
  blockquote: ({ node, ...props }) => (
    <blockquote className="my-3 border-l-2 border-border pl-3 text-muted-foreground" {...props} />
  ),
  hr: ({ node, ...props }) => <hr className="my-4 border-border" {...props} />,
  // 行内 code 给底色与圆角；代码块里的 code 由 pre 统一处理（见 pre 的 [&_code] 重置）
  code: ({ node, ...props }) => (
    <code className="rounded bg-black/5 px-1 py-0.5 text-[0.85em] dark:bg-white/10" {...props} />
  ),
  pre: ({ node, ...props }) => (
    <pre
      className="my-2 overflow-x-auto rounded-md bg-muted p-3 text-xs leading-relaxed [&_code]:bg-transparent [&_code]:p-0"
      {...props}
    />
  ),
  // 表格包进横向滚动容器：宽表横滑而非被压缩
  table: ({ node, ...props }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-xs" {...props} />
    </div>
  ),
  thead: ({ node, ...props }) => <thead className="bg-muted" {...props} />,
  th: ({ node, ...props }) => (
    <th className="whitespace-nowrap border border-border px-3 py-2 text-left font-semibold" {...props} />
  ),
  td: ({ node, ...props }) => <td className="border border-border px-3 py-2 align-top" {...props} />,
};

type Props = {
  content: string;
  className?: string;
};

export function MarkdownMessage({ content, className }: Props) {
  return (
    <div className={cn("text-sm", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
