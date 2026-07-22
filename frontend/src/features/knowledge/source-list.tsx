import React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export interface KnowledgeSourceItem {
  label: string;
  title: string;
  sourceType: string;
  sourceUrl?: string;
  contentSnippet?: string;
}

interface SourceListProps {
  sources: KnowledgeSourceItem[];
  fallbackNotice?: string;
}

export const SourceList: React.FC<SourceListProps> = ({ sources, fallbackNotice }) => {
  if (sources.length === 0 && !fallbackNotice) {
    return null;
  }

  return (
    <div className="mt-3 space-y-2">
      {fallbackNotice && (
        <div className="p-2.5 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs text-amber-600 dark:text-amber-400">
          ⚠️ {fallbackNotice}
        </div>
      )}

      {sources.length > 0 && (
        <Card className="p-3 bg-muted/30 text-xs space-y-2">
          <div className="font-semibold flex items-center justify-between text-muted-foreground">
            <span>📚 参考私有资料来源 ({sources.length})</span>
          </div>
          <div className="grid gap-2">
            {sources.map((item, idx) => (
              <div key={idx} className="p-2 bg-background border rounded flex items-start gap-2">
                <Badge variant="outline" className="font-mono text-[10px] shrink-0">
                  {item.label}
                </Badge>
                <div className="min-w-0 flex-1">
                  <div className="font-medium truncate">{item.title}</div>
                  {item.contentSnippet && (
                    <p className="text-muted-foreground text-[11px] line-clamp-2 mt-0.5">
                      {item.contentSnippet}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};
