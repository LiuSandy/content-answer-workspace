import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SessionSummary } from "@/types/workflow";

type Props = {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
};

export function ChatSessionList({ sessions, activeSessionId, onSelect, onCreate }: Props) {
  return (
    <div className="flex w-64 shrink-0 flex-col rounded-lg border bg-white">
      <div className="p-3">
        <Button className="w-full" onClick={onCreate}>
          + 新建对话
        </Button>
      </div>
      <div className="flex-1 min-h-0 space-y-1 overflow-y-auto px-2 pb-2">
        {sessions.map((session) => (
          <button
            key={session.sessionId}
            type="button"
            className={cn(
              "w-full rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-muted",
              session.sessionId === activeSessionId && "bg-muted font-medium",
            )}
            onClick={() => onSelect(session.sessionId)}
          >
            {session.title}
          </button>
        ))}
        {sessions.length === 0 && (
          <p className="px-2 py-2 text-xs text-muted-foreground">还没有会话，点上面的按钮新建一个。</p>
        )}
      </div>
    </div>
  );
}
