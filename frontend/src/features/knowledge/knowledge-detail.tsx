import React, { useState, useEffect } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { formatStatusBadge, isDocEditable } from "./types";
import type { KnowledgeDocument } from "./types";

interface KnowledgeDetailProps {
  document: KnowledgeDocument;
  markdownContent?: string;
  isCandidate?: boolean;
  onSaveMarkdown: (newMarkdown: string) => void;
  onConfirm: () => void;
  onReconvert: () => void;
  onDelete: () => void;
}

export const KnowledgeDetail: React.FC<KnowledgeDetailProps> = ({
  document,
  markdownContent = "",
  isCandidate = false,
  onSaveMarkdown,
  onConfirm,
  onReconvert,
  onDelete,
}) => {
  const [editedMd, setEditedMd] = useState(markdownContent);
  const badgeInfo = formatStatusBadge(document.status);
  const canEdit = isDocEditable(document.status);

  useEffect(() => {
    setEditedMd(markdownContent);
  }, [markdownContent]);

  return (
    <Card className="h-full flex flex-col border-none shadow-none bg-transparent">
      <CardHeader className="p-4 border-b flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="text-base font-semibold">{document.title}</CardTitle>
          <p className="text-xs text-muted-foreground mt-1">ID: {document.id}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={badgeInfo.variant}>{badgeInfo.label}</Badge>
          <Button variant="destructive" size="sm" onClick={onDelete}>
            删除资料
          </Button>
        </div>
      </CardHeader>

      <CardContent className="p-4 flex-1 flex flex-col min-h-0 space-y-4 overflow-auto">
        {document.status === "awaiting_confirmation" && (
          <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs flex justify-between items-center">
            <span>该资料包含候选 Markdown，确认后才建立检索索引。</span>
            <Button size="sm" onClick={onConfirm}>
              确认并建立索引
            </Button>
          </div>
        )}

        <Tabs defaultValue="editor" className="flex-1 flex flex-col min-h-0">
          <div className="flex justify-between items-center mb-2">
            <TabsList>
              <TabsTrigger value="editor">编辑 Markdown</TabsTrigger>
              <TabsTrigger value="info">元数据详情</TabsTrigger>
            </TabsList>

            {canEdit && (
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={onReconvert}>
                  重新转换
                </Button>
                <Button size="sm" onClick={() => onSaveMarkdown(editedMd)}>
                  保存修改
                </Button>
              </div>
            )}
          </div>

          <TabsContent value="editor" className="flex-1 min-h-0">
            <Textarea
              className="w-full h-full min-h-[400px] font-mono text-sm resize-none"
              value={editedMd}
              onChange={(e) => setEditedMd(e.target.value)}
              disabled={!canEdit}
            />
          </TabsContent>

          <TabsContent value="info" className="space-y-2 text-xs">
            <div className="grid grid-cols-2 gap-2">
              <div className="p-2 border rounded">
                <span className="text-muted-foreground block">来源类型</span>
                <span className="font-semibold uppercase">{document.sourceType}</span>
              </div>
              <div className="p-2 border rounded">
                <span className="text-muted-foreground block">修改标记</span>
                <span>{document.hasManualEdits ? "存在人工修改" : "无人工修改"}</span>
              </div>
            </div>
            {document.conversionError && (
              <div className="p-3 bg-destructive/10 text-destructive rounded border border-destructive/20">
                <strong>解析错误：</strong> {document.conversionError}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
};
