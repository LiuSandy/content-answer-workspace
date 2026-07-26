import React, { useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink, BookOpen } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export interface KnowledgeSourceItem {
  label: string;
  title: string;
  sourceType: string;
  sourceUrl?: string | null;
  contentSnippet?: string;
}

interface SourceListProps {
  sources: KnowledgeSourceItem[];
  fallbackNotice?: string | null;
  traceId?: string | null;
  showDebug?: boolean;
}

export const SourceList: React.FC<SourceListProps> = ({
  sources,
  fallbackNotice,
  traceId,
  showDebug = false,
}) => {
  const [expanded, setExpanded] = useState(false);

  if ((!sources || sources.length === 0) && !fallbackNotice) return null;

  return (
    <div className="mt-2">
      {fallbackNotice && (
        <div className="mb-1.5 text-[10px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800/40 rounded-md px-2.5 py-1.5">
          ⚠️ {fallbackNotice}
        </div>
      )}

      {sources && sources.length > 0 && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1.5 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
          >
            <BookOpen className="h-3 w-3" />
            <span className="font-medium">参考来源 ({sources.length})</span>
            {expanded ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
          </button>

          {expanded && (
            <div className="mt-1.5 space-y-1">
              {sources.map((src) => (
                <div
                  key={src.label}
                  className="flex items-start gap-2 p-2 rounded-md bg-muted/40 border border-border/50 text-[10px]"
                >
                  <Badge variant="outline" className="shrink-0 mt-0.5 font-mono text-[9px] px-1 py-0.5">
                    {src.label}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-foreground truncate flex items-center gap-1">
                      <span className="truncate">{src.title}</span>
                      {src.sourceUrl && (
                        <a
                          href={src.sourceUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="shrink-0 text-muted-foreground hover:text-primary"
                        >
                          <ExternalLink className="h-2.5 w-2.5" />
                        </a>
                      )}
                    </div>
                    {src.contentSnippet && (
                      <div className="text-muted-foreground mt-0.5 line-clamp-2 leading-relaxed">
                        {src.contentSnippet}
                      </div>
                    )}
                    <div className="mt-0.5 text-[9px] text-muted-foreground/70 uppercase tracking-wide">
                      {src.sourceType}
                    </div>
                  </div>
                </div>
              ))}

              {showDebug && traceId && (
                <div className="text-[9px] text-muted-foreground/50 px-1 pt-0.5">
                  Trace ID: <span className="font-mono">{traceId}</span>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};
