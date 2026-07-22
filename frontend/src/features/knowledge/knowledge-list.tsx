import React from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { formatStatusBadge } from "./types";
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
  if (documents.length === 0) {
    return (
      <Card className="p-8 text-center text-muted-foreground border-dashed">
        <p>暂无私有资料，请在左侧上传文件或导入网页 URL。</p>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {documents.map((doc) => {
        const badgeInfo = formatStatusBadge(doc.status);
        const isSelected = selectedDocId === doc.id;

        return (
          <Card
            key={doc.id}
            onClick={() => onSelectDoc(doc)}
            className={`cursor-pointer transition-all hover:border-primary/50 ${
              isSelected ? "border-primary bg-accent/40 shadow-sm" : ""
            }`}
          >
            <CardHeader className="p-4 pb-2 flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-sm font-medium truncate max-w-[200px]" title={doc.title}>
                {doc.title}
              </CardTitle>
              <Badge variant={badgeInfo.variant}>{badgeInfo.label}</Badge>
            </CardHeader>
            <CardContent className="p-4 pt-0 text-xs text-muted-foreground flex justify-between items-center">
              <span className="uppercase">{doc.sourceType}</span>
              <span>{new Date(doc.createdAt).toLocaleDateString()}</span>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
};
