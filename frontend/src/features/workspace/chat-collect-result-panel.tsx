import { useMemo, useState } from "react";
import { Check, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useWorkbenchStore } from "@/store/workbench-store";
import type { ChatCollectResult } from "@/types/workflow";

import {
  collectItemKey,
  getCollectGroupStats,
  getSelectedCollectItems,
  getVisibleCollectItems,
  toWorkbenchItems,
  toggleCollectSelection,
} from "./chat-collect-result-utils";

type Props = {
  result: ChatCollectResult;
};

const PLATFORM_LABEL: Record<string, string> = {
  zhihu: "知乎",
  xiaohongshu: "小红书",
};

const PLATFORM_BADGE: Record<string, string> = {
  zhihu: "border-blue-200 bg-blue-50 text-blue-700",
  xiaohongshu: "border-red-200 bg-red-50 text-red-600",
};

export function ChatCollectResultPanel({ result }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [feedback, setFeedback] = useState<string | null>(null);
  const addItems = useWorkbenchStore((s) => s.addItems);

  const items = result.items ?? [];
  const visibleItems = getVisibleCollectItems(result, expanded);
  const hiddenCount = Math.max(0, items.length - visibleItems.length);
  const groupStats = useMemo(() => getCollectGroupStats(result), [result]);
  const platformLabel = PLATFORM_LABEL[result.platform] ?? result.platform;
  const badgeClass = PLATFORM_BADGE[result.platform] ?? "border-slate-200 bg-slate-50 text-slate-600";

  function toggleItem(key: string) {
    setSelected((current) => toggleCollectSelection(current, key));
    setFeedback(null);
  }

  function toggleAll() {
    if (selected.size === items.length) {
      setSelected(new Set());
      return;
    }
    setSelected(new Set(items.map((item, index) => collectItemKey(result, item, index))));
    setFeedback(null);
  }

  function handleImport() {
    const selectedItems = getSelectedCollectItems(result, selected);
    const { added, skipped } = addItems(toWorkbenchItems(result, selectedItems));

    if (added > 0 && skipped > 0) {
      setFeedback(`已导入 ${added} 条，跳过 ${skipped} 条重复`);
    } else if (added > 0) {
      setFeedback(`已导入 ${added} 条到工作台`);
    } else if (skipped > 0) {
      setFeedback(`已跳过 ${skipped} 条重复`);
    } else {
      setFeedback("请选择要导入的条目");
    }
  }

  return (
    <div className="overflow-hidden rounded-md border bg-white">
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <span className={cn("inline-flex items-center rounded-[5px] border px-2 py-0.5 text-[11px] font-semibold", badgeClass)}>
          {platformLabel}
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">
          {result.topic || "采集结果"}
        </span>
        <span className="rounded-[4px] border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
          {items.length} 条
        </span>
      </div>

      {groupStats.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-b bg-muted/20 px-3 py-2">
          {groupStats.map((stat) => (
            <span key={stat.label} className="rounded-[4px] bg-white px-2 py-0.5 text-[11px] text-muted-foreground ring-1 ring-border">
              {stat.label} {stat.count}
            </span>
          ))}
        </div>
      )}

      <div className="divide-y">
        {visibleItems.map((item, visibleIndex) => {
          const originalIndex = items.indexOf(item);
          const itemIndex = originalIndex >= 0 ? originalIndex : visibleIndex;
          const key = collectItemKey(result, item, itemIndex);
          const isSelected = selected.has(key);

          return (
            <div
              key={key}
              className={cn(
                "flex items-start gap-2 px-3 py-2.5 transition-colors",
                isSelected ? "bg-blue-50/60" : "hover:bg-muted/30",
              )}
            >
              <button
                type="button"
                className={cn(
                  "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-[3px] border transition-colors",
                  isSelected ? "border-blue-600 bg-blue-600 text-white" : "border-border bg-white text-transparent",
                )}
                onClick={() => toggleItem(key)}
                aria-label={isSelected ? "取消选择" : "选择"}
              >
                <Check className="h-3 w-3" />
              </button>

              <button
                type="button"
                className="min-w-0 flex-1 text-left"
                onClick={() => toggleItem(key)}
              >
                <p className="line-clamp-2 text-[13px] font-medium leading-5 text-foreground">
                  {item.title}
                </p>
                {(item.metric || item.author || item.excerpt) && (
                  <p className="mt-1 line-clamp-2 text-[12px] leading-5 text-muted-foreground">
                    {[item.metric, item.author, item.excerpt].filter(Boolean).join(" · ")}
                  </p>
                )}
              </button>

              {item.url && (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                  aria-label="打开原链接"
                  onClick={(event) => event.stopPropagation()}
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
              )}
            </div>
          );
        })}
      </div>

      {hiddenCount > 0 && (
        <button
          type="button"
          className="flex w-full items-center justify-center gap-1.5 border-t bg-muted/20 py-2 text-[12px] text-muted-foreground hover:bg-muted/40 hover:text-foreground"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          {expanded ? "收起" : `查看全部 ${items.length} 条`}
        </button>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t bg-white px-3 py-2.5">
        <span className="min-w-[120px] flex-1 text-[12px] text-muted-foreground">
          {feedback ?? <>已选 <span className="font-semibold text-foreground">{selected.size}</span> / {items.length} 条</>}
        </span>
        <Button type="button" variant="outline" size="sm" className="h-7 px-2.5 text-[12px]" onClick={toggleAll}>
          {selected.size === items.length && items.length > 0 ? "取消全选" : "全选"}
        </Button>
        <Button type="button" size="sm" className="h-7 px-2.5 text-[12px]" onClick={handleImport} disabled={selected.size === 0}>
          导入已选
        </Button>
      </div>
    </div>
  );
}
