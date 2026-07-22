import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { KnowledgeList } from "./knowledge-list";
import { KnowledgeDetail } from "./knowledge-detail";
import { useKnowledgeDocuments, useKnowledgeMarkdown, useKnowledgeMutations } from "./use-knowledge";
import type { KnowledgeDocument } from "./types";

export const KnowledgePage: React.FC = () => {
  const [selectedDoc, setSelectedDoc] = useState<KnowledgeDocument | undefined>(undefined);
  const [urlModalOpen, setUrlModalOpen] = useState(false);
  const [inputUrl, setInputUrl] = useState("");

  const { data, isLoading } = useKnowledgeDocuments();
  const documents = data?.documents || [];

  const { data: markdownData } = useKnowledgeMarkdown(
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
    <div className="flex-1 flex min-h-0 h-full p-4 gap-4 bg-background text-foreground">
      {/* 左栏：上传/导入与过滤面板 */}
      <Card className="w-72 flex flex-col shrink-0 space-y-4 p-4">
        <CardHeader className="p-0 mb-2">
          <CardTitle className="text-base font-semibold">资料导入</CardTitle>
        </CardHeader>
        <CardContent className="p-0 space-y-3">
          <div>
            <Label htmlFor="file-upload" className="text-xs mb-1 block">
              上传本地文件 (PDF/MD/TXT/图片)
            </Label>
            <Input
              id="file-upload"
              type="file"
              onChange={handleFileUpload}
              className="cursor-pointer text-xs"
            />
          </div>

          <Button variant="outline" className="w-full justify-start text-xs" onClick={() => setUrlModalOpen(true)}>
            🌐 导入网页 URL
          </Button>
        </CardContent>
      </Card>

      {/* 中栏：资料列表 */}
      <Card className="w-80 flex flex-col shrink-0 p-4 min-h-0 overflow-auto">
        <CardHeader className="p-0 mb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-base font-semibold">资料列表</CardTitle>
          <span className="text-xs text-muted-foreground">共 {documents.length} 条</span>
        </CardHeader>
        <CardContent className="p-0 flex-1 min-h-0 overflow-auto">
          {isLoading ? (
            <p className="text-xs text-muted-foreground p-4 text-center">加载中...</p>
          ) : (
            <KnowledgeList
              documents={documents}
              selectedDocId={selectedDoc?.id}
              onSelectDoc={setSelectedDoc}
            />
          )}
        </CardContent>
      </Card>

      {/* 右栏：详情与 Markdown 编辑 */}
      <div className="flex-1 border rounded-xl p-4 bg-card min-h-0 overflow-auto">
        {selectedDoc ? (
          <KnowledgeDetail
            document={selectedDoc}
            markdownContent={markdownData?.markdown}
            isCandidate={selectedDoc.status === "awaiting_confirmation"}
            onSaveMarkdown={(md) => updateMarkdownMutation.mutate({ documentId: selectedDoc.id, markdown: md })}
            onConfirm={() => confirmMutation.mutate(selectedDoc.id)}
            onReconvert={() => reconvertMutation.mutate(selectedDoc.id)}
            onDelete={() => deleteMutation.mutate(selectedDoc.id)}
          />
        ) : (
          <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
            请在左侧列表选择一份资料查看或编辑
          </div>
        )}
      </div>

      {/* URL 导入对话框 (全 shadcn Dialog) */}
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
                placeholder="https://example.com/article"
                value={inputUrl}
                onChange={(e) => setInputUrl(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUrlModalOpen(false)}>
              取消
            </Button>
            <Button onClick={handleImportUrl}>确认导入</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
