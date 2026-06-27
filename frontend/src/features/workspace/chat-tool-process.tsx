import { useState } from "react";
import { ChevronRight, Wrench } from "lucide-react";

import { cn } from "@/lib/utils";

type Props = {
  steps: string[];
  // 是否为实时进行中的过程块（区别于历史回看），仅影响标题措辞
  live?: boolean;
};

/**
 * 工具调用过程的折叠展示块，默认收起。
 * 单独定义是因为工具调用属于 Agent 的内部过程，不应把原始结果当作消息直接展示，
 * 这里只用拟人化的步骤文案概述「调用了什么、是否返回」，详情按需展开。
 */
export function ChatToolProcess({ steps, live = false }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="w-fit max-w-[75%] rounded-lg border bg-muted/40 text-sm">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-muted-foreground"
      >
        <Wrench className="size-3.5" />
        <span>工具调用过程{live ? "（进行中）" : ""}</span>
        <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
      </button>
      {open ? (
        <div className="space-y-1 border-t px-3 py-2 text-muted-foreground">
          {steps.map((step, index) => (
            <p key={index}>{step}</p>
          ))}
        </div>
      ) : null}
    </div>
  );
}
