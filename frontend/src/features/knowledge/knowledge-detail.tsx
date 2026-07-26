import React, { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ReconvertDiffDialog } from "./reconvert-diff-dialog";
import type { KnowledgeDocument } from "./types";

interface KnowledgeDetailProps {
  document: KnowledgeDocument;
  markdownContent?: string;
  isMarkdownLoading?: boolean;
  isCandidate?: boolean;
  isSaving?: boolean;
  isConfirming?: boolean;
  isReconverting?: boolean;
  isDeleting?: boolean;
  onSaveMarkdown: (markdown: string) => void;
  onConfirm: () => void;
  onReconvert: () => void;
  onDelete: () => void;
}

export const KnowledgeDetail: React.FC<KnowledgeDetailProps> = ({
  document,
  markdownContent = "",
  isMarkdownLoading = false,
  isCandidate = false,
  isSaving = false,
  isConfirming = false,
  isReconverting = false,
  isDeleting = false,
  onSaveMarkdown,
  onConfirm,
  onReconvert,
  onDelete,
}) => {
  const [editorText, setEditorText] = useState(markdownContent);
  const [activeTab, setActiveTab] = useState<"editor" | "preview">("editor");
  const [diffOpen, setDiffOpen] = useState(false);

  useEffect(() => {
    setEditorText(markdownContent);
  }, [markdownContent]);

  const handleSave = () => {
    onSaveMarkdown(editorText);
  };

  const getIconText = () => {
    if (document.sourceType === "pdf" || document.title.endsWith(".pdf")) return "PDF";
    if (document.sourceType === "markdown" || document.title.endsWith(".md")) return "MD";
    if (document.sourceType === "url" || document.sourceUrl) return "URL";
    return "DOC";
  };

  // 是否有任何操作正在进行
  const isAnyBusy = isSaving || isConfirming || isReconverting || isDeleting;

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full bg-white dark:bg-card overflow-hidden">
      {/* 1. 详情头部 */}
      <div className="h-[58px] border-b border-[#e7ebf0] dark:border-border flex items-center px-[17px] gap-[11px] shrink-0">
        <div className="w-8 h-9 border border-[#dfe5ec] dark:border-border rounded-md bg-white dark:bg-card grid place-items-center text-[10px] font-bold text-[#657286] flex-none">
          {getIconText()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-bold text-[#111827] dark:text-foreground truncate">
            {document.title}
          </div>
          <div className="text-[9px] text-[#8a96a5] dark:text-muted-foreground mt-0.75 truncate">
            源文件：{document.sourceUrl || `sources/${document.id.slice(0, 4)}.../${document.title}`}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-1.75">
          {document.sourceUrl && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open(document.sourceUrl, "_blank")}
              className="h-7 text-[10px] px-2.5"
            >
              查看源文件
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled={isAnyBusy}
            onClick={() => setDiffOpen(true)}
            className="h-7 text-[10px] px-2"
          >
            {isReconverting ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin mr-1" />
                重新解析中...
              </>
            ) : (
              "重新解析 Diff"
            )}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            disabled={isAnyBusy}
            onClick={onDelete}
            className="h-7 text-[10px] px-2 min-w-[52px]"
          >
            {isDeleting ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              "删除"
            )}
          </Button>
        </div>
      </div>

      {/* 2. 警告提示框 */}
      {isCandidate && (
        <div className="mx-4 mt-3 border border-[#f0d7a5] bg-[#fffbeb] dark:bg-amber-950/20 dark:border-amber-800/40 rounded-[7px] p-2.5 flex gap-2.25 text-[#765317] dark:text-amber-300 text-[10px] leading-relaxed shrink-0">
          <span className="font-bold text-amber-600">!</span>
          <div>
            <strong className="block text-[#5f430d] dark:text-amber-200 mb-0.25">
              转换结果等待确认
            </strong>
            系统已将文档转为 Markdown。请检查并编辑内容，确认后才会进行 Chunk 切分和建立索引。
          </div>
        </div>
      )}

      {/* 3. 编辑器 Tabs 导航 */}
      <div className="h-[39px] mx-4 mt-2.75 border-b border-[#e5e9ef] dark:border-border flex items-end gap-4.25 shrink-0">
        <button
          onClick={() => setActiveTab("editor")}
          className={`h-[39px] bg-transparent font-semibold text-[10px] border-b-2 transition-colors ${
            activeTab === "editor"
              ? "text-[#1f2937] dark:text-foreground border-[#334155] dark:border-primary"
              : "text-[#8a96a5] border-transparent hover:text-foreground"
          }`}
        >
          Markdown 源码
        </button>
        <button
          onClick={() => setActiveTab("preview")}
          className={`h-[39px] bg-transparent font-semibold text-[10px] border-b-2 transition-colors ${
            activeTab === "preview"
              ? "text-[#1f2937] dark:text-foreground border-[#334155] dark:border-primary"
              : "text-[#8a96a5] border-transparent hover:text-foreground"
          }`}
        >
          GFM 视觉渲染
        </button>
        <span className="ml-auto pb-2.5 text-[9px] text-[#94a3b8] flex items-center gap-1">
          {isSaving ? (
            <>
              <Loader2 className="h-2.5 w-2.5 animate-spin" />
              保存中...
            </>
          ) : (
            "已自动保存"
          )}
        </span>
      </div>

      {/* 4. 内容区域（源码编辑 vs react-markdown 视觉预览） */}
      <div className="flex-1 mx-4 border border-[#e1e6ed] dark:border-border border-t-0 rounded-b-[7px] bg-[#fbfcfd] dark:bg-card/30 overflow-hidden min-h-0 flex flex-col">
        {isMarkdownLoading ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-2.5 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <span className="text-xs">正在加载文档内容...</span>
          </div>
        ) : activeTab === "editor" ? (
          <textarea
            value={editorText}
            onChange={(e) => setEditorText(e.target.value)}
            disabled={isAnyBusy}
            className="flex-1 w-full p-4 font-mono text-xs leading-relaxed text-[#334155] dark:text-foreground bg-transparent border-0 outline-none resize-none overflow-y-auto whitespace-pre-wrap disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder={"---\ndocument_id: ...\nsource_type: ...\n---\n# 请在此编辑 Markdown 源码..."}
          />
        ) : (
          <div className="flex-1 w-full p-5 overflow-y-auto prose dark:prose-invert max-w-none text-xs leading-normal">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {editorText}
            </ReactMarkdown>
          </div>
        )}
      </div>

      {/* 5. 底部操作栏 */}
      <div className="h-[58px] border-t border-[#e5e9ef] dark:border-border mt-3 px-4 flex items-center shrink-0">
        <span className="text-[9px] text-[#8a96a5]">
          {isCandidate
            ? "仅保存为候选 Markdown，不会建立索引"
            : "已成功建立向量与倒排索引"}
        </span>

        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={isAnyBusy}
            onClick={handleSave}
            className="h-[30px] text-[10px] px-3 min-w-[80px]"
          >
            {isSaving ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin mr-1" />
                保存中...
              </>
            ) : (
              "保存草稿"
            )}
          </Button>

          {isCandidate && (
            <Button
              size="sm"
              disabled={isAnyBusy}
              onClick={onConfirm}
              className="h-[30px] bg-[#1e293b] hover:bg-[#0f172a] text-white text-[10px] px-3.5 font-semibold min-w-[130px]"
            >
              {isConfirming ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
                  建立索引中...
                </>
              ) : (
                "✓　确认并建立索引"
              )}
            </Button>
          )}
        </div>
      </div>

      <ReconvertDiffDialog
        open={diffOpen}
        onOpenChange={setDiffOpen}
        oldMarkdown={markdownContent}
        newMarkdown={editorText}
        onApplyNew={() => {
          onReconvert();
          setDiffOpen(false);
        }}
      />
    </div>
  );
};
