import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ChatCollectItem, ChatCollectResult } from "@/types/workflow";

type Props = {
  result: ChatCollectResult;
  /** 点击「导入工作台」时触发，传入已选条目（未选则传全部） */
  onImport?: (items: ChatCollectItem[]) => void;
};

const PLATFORM_LABEL: Record<string, string> = {
  zhihu: "知乎",
  xiaohongshu: "小红书",
};

const PLATFORM_COLOR: Record<string, string> = {
  zhihu: "#0066cc",
  xiaohongshu: "#ff2442",
};

const PLATFORM_BADGE: Record<string, string> = {
  zhihu: "bg-blue-50 text-blue-600 border-blue-200",
  xiaohongshu: "bg-red-50 text-red-500 border-red-200",
};

const RANK_STYLE = [
  "bg-amber-50 text-amber-800",
  "bg-slate-100 text-slate-500",
  "bg-orange-50 text-orange-700",
];

/** 默认只展示前 5 条，其余折叠 */
const VISIBLE_COUNT = 5;

/**
 * Chat 消息流中嵌入的采集结果卡片。
 * 单独定义是因为采集结果属于结构化数据，与普通文字气泡渲染逻辑完全不同，
 * 且需要维护本地的「已选」和「展开/折叠」状态。
 */
export function ChatCollectResultCard({ result, onImport }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const platform = result.platform ?? "unknown";
  const items = result.items ?? [];
  const visibleItems = expanded ? items : items.slice(0, VISIBLE_COUNT);
  const hiddenCount = Math.max(0, items.length - VISIBLE_COUNT);

  const accentColor = PLATFORM_COLOR[platform] ?? "#64748b";
  const badgeClass = PLATFORM_BADGE[platform] ?? "bg-slate-50 text-slate-600 border-slate-200";
  const platformLabel = PLATFORM_LABEL[platform] ?? platform;

  function toggleItem(idx: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelected(selected.size === items.length ? new Set() : new Set(items.map((_, i) => i)));
  }

  function handleImport() {
    const targets = selected.size > 0 ? items.filter((_, i) => selected.has(i)) : items;
    onImport?.(targets);
  }

  return (
    <div className="w-full overflow-hidden rounded-lg border bg-white shadow-sm">
      {/* 平台色条 */}
      <div className="h-[3px] w-full" style={{ background: accentColor }} />

      {/* 卡片头 */}
      <div className="flex items-center gap-2.5 border-b px-4 py-3">
        <span className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-[5px] border px-2 py-0.5 text-[11px] font-semibold", badgeClass)}>
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: accentColor }} />
          {platformLabel}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[13.5px] font-semibold text-foreground truncate">
              {result.topic || "采集结果"}
            </span>
            <span className="shrink-0 rounded-[4px] border bg-muted px-1.5 py-0.5 font-mono text-[10.5px] text-muted-foreground">
              {items.length} 条
            </span>
          </div>
        </div>
      </div>

      {/* 内容列表 */}
      <div>
        {visibleItems.map((item, i) => {
          const isSelected = selected.has(i);
          const rankClass = RANK_STYLE[i] ?? "bg-muted text-muted-foreground";

          return (
            <div
              key={i}
              className={cn(
                "flex cursor-pointer items-start gap-2.5 border-b px-4 py-2.5 last:border-b-0 transition-colors",
                isSelected ? "bg-blue-50/60" : "hover:bg-muted/30",
              )}
              onClick={() => toggleItem(i)}
            >
              {/* 排名徽章 */}
              <span className={cn("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-[4px] font-mono text-[11px] font-medium", rankClass)}>
                {i + 1}
              </span>

              {/* 内容 */}
              <div className="flex-1 min-w-0">
                <p className="line-clamp-2 text-[13px] leading-[1.5] text-foreground mb-1">
                  {item.title}
                </p>
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  {item.metric && <span>{item.metric}</span>}
                  {item.metric && item.author && <span className="h-2.5 w-px bg-border" />}
                  {item.author && <span className="truncate max-w-[80px]">{item.author}</span>}
                  {/* 热度条仅前 3 名显示 */}
                  {i < 3 && items.length > 1 && (
                    <>
                      <span className="h-2.5 w-px bg-border" />
                      <div className="h-[3px] w-10 overflow-hidden rounded-full bg-border">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-amber-400 to-red-400"
                          style={{ width: `${100 - i * 28}%` }}
                        />
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* 复选框 */}
              <div className={cn(
                "mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border-[1.5px] transition-all",
                isSelected ? "border-blue-600 bg-blue-600" : "border-border bg-white",
              )}>
                {isSelected && (
                  <svg width="8" height="6" viewBox="0 0 8 6" fill="none">
                    <path d="M1 3L3 5L7 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 展开/折叠 */}
      {hiddenCount > 0 && (
        <button
          type="button"
          className="flex w-full items-center justify-center gap-1.5 border-t bg-muted/30 py-2 text-[11.5px] text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? (
            <><ChevronUp className="h-3 w-3" />收起</>
          ) : (
            <><ChevronDown className="h-3 w-3" />查看全部 {items.length} 条</>
          )}
        </button>
      )}

      {/* 操作栏 */}
      <div className="flex items-center gap-2 border-t bg-white px-4 py-2.5">
        <span className="flex-1 font-mono text-[11px] text-muted-foreground">
          已选 <span className="font-medium text-foreground">{selected.size}</span> / {items.length} 条
        </span>
        <Button variant="outline" size="sm" className="h-7 text-[12px]" onClick={toggleSelectAll}>
          {selected.size === items.length && items.length > 0 ? "取消全选" : "全选"}
        </Button>
        <Button size="sm" className="h-7 text-[12px]" onClick={handleImport}>
          导入工作台
        </Button>
      </div>
    </div>
  );
}
