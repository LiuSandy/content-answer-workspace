import React, { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { KnowledgeList } from "./knowledge-list";
import { KnowledgeDetail } from "./knowledge-detail";
import { useKnowledgeDocuments, useKnowledgeMarkdown, useKnowledgeMutations } from "./use-knowledge";
import type { KnowledgeDocument } from "./types";

export const KnowledgePage: React.FC = () => {
  const [selectedDoc, setSelectedDoc] = useState<KnowledgeDocument | undefined>(undefined);
  const [urlModalOpen, setUrlModalOpen] = useState(false);
  const [inputUrl, setInputUrl] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");

  const { data, isLoading } = useKnowledgeDocuments();
  const allDocuments = data?.documents || [];

  const filteredDocuments = allDocuments.filter((doc) => {
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const nameMatch = doc.title?.toLowerCase().includes(q);
      const urlMatch = doc.sourceUrl?.toLowerCase().includes(q);
      if (!nameMatch && !urlMatch) return false;
    }
    if (statusFilter !== "all") {
      if (doc.status !== statusFilter) return false;
    }
    if (typeFilter !== "all") {
      if (typeFilter === "markdown" && doc.sourceType !== "markdown" && !doc.title.endsWith(".md")) return false;
      if (typeFilter === "pdf" && doc.sourceType !== "pdf" && !doc.title.endsWith(".pdf")) return false;
      if (typeFilter === "url" && doc.sourceType !== "url" && !doc.sourceUrl) return false;
      if (typeFilter === "image" && doc.sourceType !== "image" && !doc.title.match(/\.(png|jpg|jpeg)$/i)) return false;
    }
    return true;
  });

  const awaitingCount = allDocuments.filter((d) => d.status === "awaiting_confirmation").length;
  const readyCount = allDocuments.filter((d) => d.status === "available").length;
  const failCount = allDocuments.filter((d) => d.status === "failed").length;

  const { data: markdownData, isLoading: isMarkdownLoading } = useKnowledgeMarkdown(
    selectedDoc?.id,
    selectedDoc?.status === "awaiting_confirmation"
  );

  const {
    uploadMutation,
    importUrlMutation,
    updateMarkdownMutation,
    confirmMutation,
    reconvertMutation,
    deleteMutation,
  } = useKnowledgeMutations();

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
      e.target.value = "";
    }
  };

  const handleImportUrl = () => {
    if (inputUrl.trim()) {
      importUrlMutation.mutate(inputUrl.trim(), {
        onSuccess: () => {
          setUrlModalOpen(false);
          setInputUrl("");
        },
      });
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 h-full w-full bg-white dark:bg-background text-[#111827] dark:text-foreground font-sans p-0 m-0 overflow-hidden">
      {/* 1. 功能标题与搜索行 (.kb-pagebar) */}
      <div className="h-[58px] bg-white dark:bg-card border-b border-[#e5e9ef] dark:border-border flex items-center px-5 gap-3.5 shrink-0">
        <div>
          <div className="text-sm font-bold">私有资料库</div>
          <div className="text-[10px] text-[#7b8797] dark:text-muted-foreground mt-0.5">
            管理 Agent 创作时可检索和引用的个人资料
          </div>
        </div>

        <div className="ml-auto relative w-[240px] flex items-center">
          <Input
            type="text"
            placeholder="⌕　搜索标题、来源或内容"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-8 text-[11px] bg-[#fbfcfd] dark:bg-secondary border-[#e0e5ec] dark:border-input rounded-md px-2.5 placeholder:text-[#94a3b8]"
          />
        </div>

        {/* ＋ 添加资料按钮（带 Loading 状态） */}
        <div className="relative">
          <input
            type="file"
            id="kb-file-input"
            disabled={uploadMutation.isPending}
            onChange={handleFileUpload}
            className="hidden"
          />
          <Button
            disabled={uploadMutation.isPending}
            onClick={() => document.getElementById("kb-file-input")?.click()}
            className="h-8 bg-[#1e293b] hover:bg-[#0f172a] text-white text-xs font-semibold px-3 rounded-md min-w-[100px]"
          >
            {uploadMutation.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
                上传解析中...
              </>
            ) : (
              "＋　添加资料"
            )}
          </Button>
        </div>

        {/* 🌐 导入 URL 按钮 */}
        <Button
          variant="outline"
          onClick={() => setUrlModalOpen(true)}
          className="h-8 text-xs px-2.5"
        >
          🌐 导入 URL
        </Button>
      </div>

      {/* 2. 三栏主体工作区 (.kb-body) */}
      <div className="flex-1 grid grid-cols-[190px_350px_minmax(430px,1fr)] bg-white dark:bg-card min-h-0 overflow-hidden">
        
        {/* 左栏：筛选侧边栏 */}
        <aside className="border-r border-[#e5e9ef] dark:border-border bg-[#fbfcfd] dark:bg-card/50 p-3.5 space-y-1 overflow-y-auto min-h-0">
          <div className="text-[9px] tracking-wider uppercase text-[#94a3b8] font-bold px-2 mb-2">
            资料状态
          </div>

          <button
            onClick={() => setStatusFilter("all")}
            className={`w-full h-8.5 rounded-md flex items-center gap-2 px-2.5 text-[11px] mb-0.5 transition-colors ${
              statusFilter === "all"
                ? "bg-[#e9edf3] text-[#1f2937] font-semibold"
                : "text-[#526071] hover:bg-muted/50"
            }`}
          >
            <span>▦</span> 全部资料
            <span className="ml-auto text-[9px] text-[#8a96a5] bg-white dark:bg-secondary border border-[#e5e9ef] dark:border-border rounded px-1.5 py-0.25">
              {allDocuments.length}
            </span>
          </button>

          <button
            onClick={() => setStatusFilter("awaiting_confirmation")}
            className={`w-full h-8.5 rounded-md flex items-center gap-2 px-2.5 text-[11px] mb-0.5 transition-colors ${
              statusFilter === "awaiting_confirmation"
                ? "bg-[#e9edf3] text-[#1f2937] font-semibold"
                : "text-[#526071] hover:bg-muted/50"
            }`}
          >
            <span className="w-1.75 h-1.75 rounded-full bg-[#d97706]"></span>
            待确认
            <span className="ml-auto text-[9px] text-[#8a96a5] bg-white dark:bg-secondary border border-[#e5e9ef] dark:border-border rounded px-1.5 py-0.25">
              {awaitingCount}
            </span>
          </button>

          <button
            onClick={() => setStatusFilter("available")}
            className={`w-full h-8.5 rounded-md flex items-center gap-2 px-2.5 text-[11px] mb-0.5 transition-colors ${
              statusFilter === "available"
                ? "bg-[#e9edf3] text-[#1f2937] font-semibold"
                : "text-[#526071] hover:bg-muted/50"
            }`}
          >
            <span className="w-1.75 h-1.75 rounded-full bg-[#059669]"></span>
            已索引
            <span className="ml-auto text-[9px] text-[#8a96a5] bg-white dark:bg-secondary border border-[#e5e9ef] dark:border-border rounded px-1.5 py-0.25">
              {readyCount}
            </span>
          </button>

          <button
            onClick={() => setStatusFilter("failed")}
            className={`w-full h-8.5 rounded-md flex items-center gap-2 px-2.5 text-[11px] mb-0.5 transition-colors ${
              statusFilter === "failed"
                ? "bg-[#e9edf3] text-[#1f2937] font-semibold"
                : "text-[#526071] hover:bg-muted/50"
            }`}
          >
            <span className="w-1.75 h-1.75 rounded-full bg-[#dc2626]"></span>
            处理失败
            <span className="ml-auto text-[9px] text-[#8a96a5] bg-white dark:bg-secondary border border-[#e5e9ef] dark:border-border rounded px-1.5 py-0.25">
              {failCount}
            </span>
          </button>

          <div className="h-px bg-[#e8ecf1] dark:bg-border my-3 mx-2"></div>

          <div className="text-[9px] tracking-wider uppercase text-[#94a3b8] font-bold px-2 mb-2">
            来源类型
          </div>

          {[
            { id: "all", label: "全部类型", icon: "▦" },
            { id: "markdown", label: "Markdown", icon: "📄" },
            { id: "pdf", label: "PDF 文档", icon: "📕" },
            { id: "url", label: "网页文章", icon: "🌐" },
            { id: "image", label: "图片素材", icon: "🖼️" },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => setTypeFilter(item.id)}
              className={`w-full h-8.5 rounded-md flex items-center gap-2 px-2.5 text-[11px] mb-0.5 transition-colors ${
                typeFilter === item.id
                  ? "bg-[#e9edf3] text-[#1f2937] font-semibold"
                  : "text-[#526071] hover:bg-muted/50"
              }`}
            >
              <span className="text-xs">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </aside>

        {/* 中栏：资料列表 */}
        <section className="border-r border-[#e5e9ef] dark:border-border flex flex-col min-w-0 bg-white dark:bg-card min-h-0">
          {isLoading ? (
            <div className="p-8 text-center text-xs text-muted-foreground flex flex-col items-center gap-2">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              加载资料列表中...
            </div>
          ) : (
            <KnowledgeList
              documents={filteredDocuments}
              selectedDocId={selectedDoc?.id}
              onSelectDoc={setSelectedDoc}
            />
          )}
        </section>

        {/* 右栏：资料详情 */}
        <section className="flex flex-col min-w-0 bg-white dark:bg-card overflow-hidden min-h-0">
          {selectedDoc ? (
            <KnowledgeDetail
              document={selectedDoc}
              markdownContent={markdownData?.markdown}
              isMarkdownLoading={isMarkdownLoading}
              isCandidate={selectedDoc.status === "awaiting_confirmation"}
              isSaving={updateMarkdownMutation.isPending}
              isConfirming={confirmMutation.isPending}
              isReconverting={reconvertMutation.isPending}
              isDeleting={deleteMutation.isPending}
              onSaveMarkdown={(md) => updateMarkdownMutation.mutate({ documentId: selectedDoc.id, markdown: md })}
              onConfirm={() => confirmMutation.mutate(selectedDoc.id)}
              onReconvert={() => reconvertMutation.mutate(selectedDoc.id)}
              onDelete={() => {
                deleteMutation.mutate(selectedDoc.id, {
                  onSuccess: () => setSelectedDoc(undefined),
                });
              }}
            />
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-muted-foreground text-xs gap-2 p-4">
              <span className="text-3xl opacity-60">📁</span>
              请在中间列表中选择一份资料查看或编辑
            </div>
          )}
        </section>
      </div>

      {/* URL 导入 Dialog */}
      <Dialog open={urlModalOpen} onOpenChange={setUrlModalOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>导入网页 URL</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="url-input">网页地址</Label>
              <Input
                id="url-input"
                disabled={importUrlMutation.isPending}
                placeholder="https://example.com/article"
                value={inputUrl}
                onChange={(e) => setInputUrl(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={importUrlMutation.isPending}
              onClick={() => setUrlModalOpen(false)}
            >
              取消
            </Button>
            <Button
              disabled={importUrlMutation.isPending}
              onClick={handleImportUrl}
              className="min-w-[90px]"
            >
              {importUrlMutation.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
                  抓取中...
                </>
              ) : (
                "确认导入"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
