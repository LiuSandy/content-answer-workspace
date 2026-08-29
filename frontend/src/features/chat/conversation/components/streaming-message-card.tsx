import React, { useLayoutEffect, useSyncExternalStore } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Loader2, AlertCircle } from "lucide-react";
import { MarkdownContent } from "@/components/ui/markdown-content";
import { decorateStreamingMarkdown } from "../model/markdown-stream-decorator";
import type { StreamingMessageController } from "../model/streaming-message-controller";

export interface StreamingMessageCardProps {
  controller: StreamingMessageController;
  markdownComponents: any;
  renderSourceList?: (data: unknown) => React.ReactNode;
  onContentChange?: () => void;
}

/** 唯一订阅高频流式快照的展示组件。 */
export const StreamingMessageCard = React.memo(function StreamingMessageCard({
  controller,
  markdownComponents,
  renderSourceList,
  onContentChange,
}: StreamingMessageCardProps) {
  const snapshot = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );

  const { visible, agentStatus, streamingText, streamingSourceList, streamingError } = snapshot;
  const decoratedText = decorateStreamingMarkdown(streamingText);

  // DOM 提交后通知滚动守卫；该回调只执行命令，不更新 ChatPanel state。
  useLayoutEffect(() => {
    if (visible) onContentChange?.();
  }, [visible, agentStatus, streamingText, streamingSourceList, streamingError, onContentChange]);

  if (!visible) return null;

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
              <MarkdownContent components={markdownComponents}>{decoratedText}</MarkdownContent>
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
