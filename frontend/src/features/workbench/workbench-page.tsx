import { LayoutDashboard } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useWorkbenchStore } from "@/store/workbench-store";

import { WorkbenchAnswerPanel } from "./workbench-answer-panel";
import { WorkbenchQuestionList } from "./workbench-question-list";
import { WorkbenchUrlImportBar } from "./workbench-url-import-bar";

/** 工作台页面：汇聚采集页和 URL 导入的问题，统一生成 AI 回答。 */
export function WorkbenchPage() {
  const { items } = useWorkbenchStore();
  const doneCount = items.filter((i) => Boolean(i.answer?.trim())).length;

  return (
    <section className="flex flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* 页面标题栏 */}
      <div className="flex items-center justify-between gap-4 border-b border-slate-200 bg-slate-50/60 px-5 py-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-100">
            <LayoutDashboard className="h-3.5 w-3.5 text-slate-600" />
          </div>
          <div>
            <span className="text-[14px] font-semibold text-slate-800">工作台</span>
            <span className="ml-2 text-[12px] text-slate-400">
              从采集页或 URL 导入问题，批量生成 AI 回答
            </span>
          </div>
        </div>
        {items.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-medium text-slate-500">
              {doneCount}/{items.length} 已生成
            </span>
            <Badge
              variant="secondary"
              className="rounded-[6px] px-2 py-0.5 text-[11px] font-semibold"
            >
              {items.length} 个问题
            </Badge>
          </div>
        )}
      </div>

      {/* URL 导入栏 */}
      <WorkbenchUrlImportBar />

      {/* 主体：左侧列表 + 右侧回答区 */}
      <div className="flex-1 min-h-0 grid xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="flex flex-col overflow-hidden border-r border-slate-200 p-4">
          <WorkbenchQuestionList />
        </div>
        <div className="overflow-y-auto p-4">
          <WorkbenchAnswerPanel />
        </div>
      </div>
    </section>
  );
}
