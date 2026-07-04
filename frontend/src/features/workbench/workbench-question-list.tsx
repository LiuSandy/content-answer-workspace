import { useDeferredValue, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { useWorkbenchStore, type PlatformFilter, type StatusFilter } from "@/store/workbench-store";
import type { WorkbenchItem } from "@/types/workflow";

const PLATFORM_LABELS: Record<string, string> = {
  all: "全部",
  zhihu: "知乎",
  xiaohongshu: "小红书",
};

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "pending", label: "未生成" },
  { value: "done", label: "已生成" },
];

function WorkbenchQuestionRow({
  item,
  active,
  onSelect,
}: {
  item: WorkbenchItem;
  active: boolean;
  onSelect: (id: string) => void;
}) {
  const status = item.generationStatus ?? (item.answer?.trim() ? "done" : "idle");
  const generated = status === "done";
  const statusLabel: Record<typeof status, string> = {
    idle: "待生成",
    generating: "生成中",
    done: "已生成",
    error: "生成失败",
    interrupted: "已中断",
  };
  const statusClass =
    status === "done"
      ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
      : status === "error" || status === "interrupted"
        ? "bg-red-50 text-red-700 ring-1 ring-red-200"
        : status === "generating"
          ? "bg-blue-50 text-blue-700 ring-1 ring-blue-200"
          : "bg-amber-50 text-amber-700 ring-1 ring-amber-200";
  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      className={cn(
        "w-full rounded-md border bg-white px-3 py-2.5 text-left transition-all hover:border-slate-300 hover:bg-slate-50/70",
        active
          ? "border-blue-500 bg-blue-50/40 ring-1 ring-blue-500/20 hover:bg-blue-50/40"
          : "border-slate-200",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <span
              className={cn(
                "inline-flex items-center rounded-[4px] px-1.5 py-[1px] text-[10px] font-semibold",
                statusClass,
              )}
            >
              {statusLabel[status]}
            </span>
            <span className="text-[11px] text-slate-400">
              {PLATFORM_LABELS[item.sourcePlatform] ?? item.sourcePlatform}
            </span>
          </div>
          <div className="line-clamp-2 text-[13px] font-semibold leading-[1.5] text-slate-800">
            {item.title}
          </div>
          {item.excerpt && (
            <div className="line-clamp-1 text-[12px] text-slate-500">{item.excerpt}</div>
          )}
          {item.sourceTopic && (
            <span className="rounded-[4px] bg-slate-100 px-1.5 py-[1px] text-[10px] font-medium text-slate-500">
              {item.sourceTopic}
            </span>
          )}
        </div>
        <span
          className={cn(
            "mt-1 h-[7px] w-[7px] shrink-0 rounded-full",
            generated
              ? "bg-emerald-400"
              : status === "error" || status === "interrupted"
                ? "bg-red-400"
                : status === "generating"
                  ? "bg-blue-400"
                  : "bg-amber-300",
          )}
        />
      </div>
    </button>
  );
}

/** 工作台左侧问题列表，含平台 Tab、状态筛选、搜索和分页。 */
export function WorkbenchQuestionList() {
  const {
    items,
    selectedItemId,
    statusFilter,
    platformFilter,
    searchKeyword,
    setStatusFilter,
    setPlatformFilter,
    setSearchKeyword,
    selectItem,
  } = useWorkbenchStore();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const deferredKeyword = useDeferredValue(searchKeyword);

  const filtered = useMemo(() => {
    let result = items;
    if (platformFilter !== "all") {
      result = result.filter((i) => i.sourcePlatform === platformFilter);
    }
    if (statusFilter === "pending") {
      result = result.filter((i) => (i.generationStatus ?? (i.answer?.trim() ? "done" : "idle")) !== "done");
    } else if (statusFilter === "done") {
      result = result.filter((i) => (i.generationStatus ?? (i.answer?.trim() ? "done" : "idle")) === "done");
    }
    const kw = deferredKeyword.trim().toLowerCase();
    if (kw) {
      result = result.filter((i) =>
        `${i.title} ${i.excerpt} ${i.sourceTopic}`.toLowerCase().includes(kw),
      );
    }
    return result;
  }, [items, platformFilter, statusFilter, deferredKeyword]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pageStart = (currentPage - 1) * pageSize;
  const paged = filtered.slice(pageStart, pageStart + pageSize);
  const visibleStart = filtered.length ? pageStart + 1 : 0;
  const visibleEnd = Math.min(pageStart + pageSize, filtered.length);

  function handlePlatformChange(v: string) {
    setPlatformFilter(v as PlatformFilter);
    setPage(1);
  }

  function handleSearch(v: string) {
    setSearchKeyword(v);
    setPage(1);
  }

  return (
    <div className="h-full flex flex-col gap-3">
      {/* 搜索栏 */}
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
        <Input
          value={searchKeyword}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="搜索标题、摘要、主题"
          className="h-8 rounded-md border-slate-200 bg-white pl-8 text-[12px] shadow-none focus-visible:ring-1 focus-visible:ring-blue-500"
        />
      </div>

      {/* 状态筛选 chips */}
      <div className="flex gap-1">
        {STATUS_FILTERS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            onClick={() => { setStatusFilter(value); setPage(1); }}
            className={cn(
              "rounded-[4px] px-2 py-[3px] text-[11px] font-medium transition-colors",
              statusFilter === value
                ? "bg-slate-800 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* 平台 Tabs */}
      <Tabs value={platformFilter} onValueChange={handlePlatformChange}>
        <TabsList className="h-8 w-full rounded-md bg-slate-100 p-0.5">
          {(["all", "zhihu", "xiaohongshu"] as const).map((p) => (
            <TabsTrigger
              key={p}
              value={p}
              className="flex-1 rounded-[5px] text-[11px] font-medium data-[state=active]:bg-white data-[state=active]:shadow-sm"
            >
              {PLATFORM_LABELS[p]}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* 问题列表 */}
      <div className="flex-1 space-y-2 overflow-y-auto pr-0.5">
        {items.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-200 bg-slate-50/60 px-3 py-3.5 text-center text-[12px] text-slate-400">
            工作台为空。从采集页勾选问题，或在上方粘贴 URL 导入。
          </div>
        ) : paged.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-200 bg-slate-50/60 px-3 py-3.5 text-[12px] text-slate-400">
            没有匹配的问题结果。
          </div>
        ) : (
          paged.map((item) => (
            <WorkbenchQuestionRow
              key={item.id}
              item={item}
              active={item.id === selectedItemId}
              onSelect={selectItem}
            />
          ))
        )}
      </div>

      {/* 底部分页 */}
      <div className="flex items-center justify-between gap-2 border-t border-slate-200 pt-2">
        <span className="text-[11px] text-slate-400">
          {filtered.length ? `${visibleStart}–${visibleEnd} / ${filtered.length}` : "0 / 0"}
        </span>
        <div className="flex items-center gap-1.5">
          <Select
            value={String(pageSize)}
            onValueChange={(v) => { setPageSize(Number(v)); setPage(1); }}
          >
            <SelectTrigger className="h-7 w-[90px] rounded-md border-slate-200 bg-white text-[11px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[10, 20, 50].map((s) => (
                <SelectItem key={s} value={String(s)} className="text-[12px]">
                  每页 {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="icon"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
            className="h-7 w-7 rounded-md border-slate-200 bg-white"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
          <span className="min-w-[36px] text-center text-[11px] font-medium text-slate-500">
            {currentPage}/{totalPages}
          </span>
          <Button
            variant="outline"
            size="icon"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages}
            className="h-7 w-7 rounded-md border-slate-200 bg-white"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
