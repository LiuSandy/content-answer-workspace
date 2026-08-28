import React, { useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Loader2, AlertCircle } from "lucide-react";
import { MarkdownContent } from "@/components/ui/markdown-content";
import { decorateStreamingMarkdown } from "./markdown-stream-decorator";

export interface StreamingMessageCardProps {
  isStreaming: boolean;
  agentStatus: string | null;
  streamingText: string;
  streamingSourceList: any | null;
  streamingError: string | null;
  markdownComponents: any;
  renderSourceList?: (data: any) => React.ReactNode;
}

/**
 * 独立的流式消息卡片组件：
 * 1. 状态与渲染局部化：将打字机高频刷新的局部 DOM 从主面板隔离；
 * 2. 语法虚拟补齐：通过 decorateStreamingMarkdown 防止流式语法未闭合引起的布局跳变；
 * 3. 记忆化：使用 React.memo 避免非必要属性未变时的重新渲染。
 */
export const StreamingMessageCard = React.memo(function StreamingMessageCard({
  isStreaming,
  agentStatus,
  streamingText,
  streamingSourceList,
  streamingError,
  markdownComponents,
  renderSourceList,
}: StreamingMessageCardProps) {
  if (!isStreaming && !streamingError) {
    return null;
  }

  // 虚拟补齐未闭合语法（代码块、LaTeX 公式、加粗等）
  const decoratedText = useMemo(() => {
    return decorateStreamingMarkdown(streamingText);
  }, [streamingText]);

  return (
    <div className="flex justify-start w-full">
      <Card className="max-w-[calc(100%-3rem)] w-full border-none bg-card shadow-sm">
        <CardContent className="p-3.5">
          {agentStatus && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              {agentStatus}
            </div>
          )}
          {decoratedText ? (
            <div className="text-sm leading-relaxed max-w-none text-foreground/90">
              <MarkdownContent components={markdownComponents}>
                {decoratedText}
              </MarkdownContent>
            </div>
          ) : null}
          {streamingSourceList && renderSourceList ? (
            <div className={decoratedText ? "mt-4 pt-3 border-t border-border/30" : ""}>
              {renderSourceList(streamingSourceList)}
            </div>
          ) : null}
          {streamingError && (
            <div className="flex items-start gap-2.5 text-destructive bg-destructive/5 border border-destructive/20 rounded-xl p-3 w-full">
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold">请求出错</p>
                <p className="mt-1 text-xs leading-relaxed opacity-90">{streamingError}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
});
