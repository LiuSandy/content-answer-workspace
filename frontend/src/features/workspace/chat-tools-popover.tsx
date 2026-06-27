import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";

import { listAgentTools } from "./workflow-api";

/**
 * 聊天输入框左下角的「工具」按钮 + 只读工具清单弹层。
 * 单独定义是因为这是一段自包含的展示逻辑（拉取工具、点击展开、点击外部收起），
 * 不属于输入框的发送职责，抽出后输入框只关心消息收发。
 */
export function ChatToolsPopover() {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // 工具清单基本不变，开启缓存即可；仅在面板首次展开时才有展示价值
  const toolsQuery = useQuery({
    queryKey: ["agent-tools"],
    queryFn: listAgentTools,
  });
  const tools = toolsQuery.data ?? [];

  // 点击弹层外部时收起；仅在展开状态挂载监听，避免无谓的全局事件开销
  useEffect(() => {
    if (!open) {
      return;
    }
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <Button type="button" variant="ghost" size="sm" onClick={() => setOpen((prev) => !prev)}>
        <Wrench />
        工具{tools.length > 0 ? ` (${tools.length})` : ""}
      </Button>

      {open ? (
        <div className="absolute bottom-full left-0 z-50 mb-2 max-h-72 w-72 overflow-y-auto rounded-lg border bg-card p-1 shadow-md">
          {toolsQuery.isLoading ? (
            <p className="px-2 py-1.5 text-sm text-muted-foreground">加载中…</p>
          ) : null}
          {!toolsQuery.isLoading && tools.length === 0 ? (
            <p className="px-2 py-1.5 text-sm text-muted-foreground">暂无可用工具</p>
          ) : null}
          {tools.map((tool) => (
            <div key={tool.name} className="rounded-md px-2 py-1.5 hover:bg-muted/60">
              <p className="text-sm font-medium text-foreground">{tool.name}</p>
              <p className="line-clamp-2 text-xs text-muted-foreground">{tool.description}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
