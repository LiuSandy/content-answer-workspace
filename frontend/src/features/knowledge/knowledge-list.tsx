import React, { useState } from "react";
import type { KnowledgeDocument } from "./types";

interface KnowledgeListProps {
  documents: KnowledgeDocument[];
  selectedDocId?: string;
  onSelectDoc: (doc: KnowledgeDocument) => void;
}

export const KnowledgeList: React.FC<KnowledgeListProps> = ({
  documents,
  selectedDocId,
  onSelectDoc,
}) => {
  const [sortAsc, setSortAsc] = useState(false);

  const sortedDocs = [...documents].sort((a, b) => {
    const timeA = new Date(a.updatedAt || a.createdAt || 0).getTime();
    const timeB = new Date(b.updatedAt || b.createdAt || 0).getTime();
    return sortAsc ? timeA - timeB : timeB - timeA;
  });

  const getIconText = (doc: KnowledgeDocument) => {
    if (doc.sourceType === "pdf" || doc.title.endsWith(".pdf")) return "PDF";
    if (doc.sourceType === "markdown" || doc.title.endsWith(".md")) return "MD";
    if (doc.sourceType === "url" || doc.sourceUrl) return "URL";
    if (doc.sourceType === "image" || doc.title.match(/\.(png|jpg|jpeg)$/i)) return "IMG";
    return "DOC";
  };

  const renderStatusTag = (status: KnowledgeDocument["status"]) => {
    switch (status) {
      case "awaiting_confirmation":
        return (
          <span className="inline-flex items-center rounded text-[8px] font-bold px-1.25 py-0.5 mt-1.75 bg-[#fff7e6] text-[#a15c00] border border-[#f3d8a6]">
            待确认 Markdown
          </span>
        );
      case "available":
        return (
          <span className="inline-flex items-center rounded text-[8px] font-bold px-1.25 py-0.5 mt-1.75 bg-[#ecfdf5] text-[#047857] border border-[#b7ead5]">
            已建立索引
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center rounded text-[8px] font-bold px-1.25 py-0.5 mt-1.75 bg-[#fff1f2] text-[#be123c] border border-[#fecdd3]">
            识别质量较低 / 失败
          </span>
        );
      case "indexing":
      case "pending":
      default:
        return (
          <span className="inline-flex items-center rounded text-[8px] font-bold px-1.25 py-0.5 mt-1.75 bg-[#eff6ff] text-[#1d4ed8] border border-[#bfdbfe]">
            解析处理中...
          </span>
        );
    }
  };

  const stageLabel = (stage?: string) => {
    const labels: Record<string, string> = {
      discovered: "等待处理",
      recovering: "恢复处理中",
      preparing: "准备文件",
      hashing: "校验源文件",
      parsing: "识别 Markdown",
      initializing_pages: "初始化 PDF 页面",
      parsing_pages: "逐页识别 PDF",
      merging_markdown: "合并页面 Markdown",
      saving_candidate: "保存候选稿",
      saving_markdown: "保存 Markdown",
      dispatching_index: "提交索引",
      completed: "处理完成",
      failed: "处理失败",
    };
    return stage ? labels[stage] || stage : "";
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-white dark:bg-card">
      <div className="h-11 flex items-center px-3.5 border-b border-[#edf0f4] dark:border-border text-[10px] text-[#778395] shrink-0">
        <span>最近更新</span>
        <button
          onClick={() => setSortAsc(!sortAsc)}
          className="ml-auto hover:text-foreground transition-colors flex items-center gap-1"
        >
          {documents.length} 份资料　{sortAsc ? "↑" : "↕"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 divide-y divide-[#edf0f4] dark:divide-border">
        {sortedDocs.length === 0 ? (
          <div className="p-6 text-center text-xs text-muted-foreground">
            暂无匹配资料
          </div>
        ) : (
          sortedDocs.map((doc) => {
            const isSelected = doc.id === selectedDocId;
            return (
              <div
                key={doc.id}
                onClick={() => onSelectDoc(doc)}
                className={`p-3.25 px-3.5 flex gap-2.75 cursor-pointer transition-colors ${
                  isSelected
                    ? "bg-[#f1f4f8] dark:bg-accent/40 [box-shadow:inset_3px_0_#334155]"
                    : "hover:bg-[#f8fafc] dark:hover:bg-muted/40"
                }`}
              >
                <div className="w-8 h-9 border border-[#dfe5ec] dark:border-border rounded-md bg-white dark:bg-card grid place-items-center text-[10px] font-bold text-[#657286] dark:text-muted-foreground flex-none shadow-xs">
                  {getIconText(doc)}
                </div>

                <div className="min-w-0 flex-1">
                  <div className="text-[11px] font-semibold text-[#111827] dark:text-foreground truncate">
                    {doc.title}
                  </div>
                  <div className="text-[9px] text-[#8a96a5] dark:text-muted-foreground mt-1">
                    更新于 · {new Date(doc.updatedAt || doc.createdAt || Date.now()).toLocaleDateString()}
                  </div>
                  {renderStatusTag(doc.status)}
                  {doc.sourceFile?.job && ["queued", "running"].includes(doc.sourceFile.job.status) ? (
                    <div className="mt-1.5">
                      <div className="flex items-center justify-between text-[9px] text-[#64748b]">
                        <span>{stageLabel(doc.sourceFile.job.stage)}</span>
                        <span>{doc.sourceFile.job.progressPercent}%</span>
                      </div>
                      <div className="mt-1 h-1 rounded-full bg-[#e2e8f0] overflow-hidden">
                        <div
                          className="h-full bg-[#3b82f6] transition-[width]"
                          style={{ width: `${doc.sourceFile.job.progressPercent}%` }}
                        />
                      </div>
                      {doc.sourceFile.job.totalPages > 0 ? (
                        <div className="mt-1 text-[9px] text-[#64748b]">
                          已完成 {doc.sourceFile.job.completedPages}/{doc.sourceFile.job.totalPages} 页
                          <span className="ml-1.5 text-[#059669]">成功 {doc.sourceFile.job.succeededPages}</span>
                          {doc.sourceFile.job.failedPages > 0 ? (
                            <span className="ml-1.5 text-[#be123c]">失败 {doc.sourceFile.job.failedPages}</span>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {doc.sourceFile?.job?.status === "completed_with_errors" ? (
                    <div className="mt-1 text-[9px] text-[#b45309]">
                      识别完成，{doc.sourceFile.job.failedPages} 页失败，请确认前校对
                    </div>
                  ) : null}
                  {doc.sourceFile?.failureReason ? (
                    <div className="mt-1 text-[9px] text-[#be123c] line-clamp-2" title={doc.sourceFile.failureReason}>
                      {doc.sourceFile.failureReason}
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
