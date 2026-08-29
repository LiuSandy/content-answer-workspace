import { useEffect } from "react";
import { useParams } from "react-router-dom";

import { ChatSidebar } from "./sessions/chat-sidebar";
import { ChatPanel } from "./conversation/components/chat-panel";
import { EditorPanel } from "./editor/components/editor-panel";
import { TodayOpportunitiesBanner } from "./components/today-opportunities-banner";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { useChatStore } from "@/store/chat-store";

export function ChatWorkspace() {
  const { chatId } = useParams<{ chatId: string }>();
  const { selectedSourceItemId, setCurrentChatId } = useChatStore();
  const showEditor = selectedSourceItemId !== null;

  useEffect(() => {
    setCurrentChatId(chatId || null);
  }, [chatId, setCurrentChatId]);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <TodayOpportunitiesBanner />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <ChatSidebar />
        {showEditor ? (
          <ResizablePanelGroup orientation="horizontal" className="flex-1">
            <ResizablePanel
              defaultSize={50}
              minSize={30}
              className="flex flex-col min-h-0 overflow-hidden"
            >
              <ChatPanel />
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel
              defaultSize={50}
              minSize={30}
              className="flex flex-col min-h-0 overflow-hidden"
            >
              <EditorPanel />
            </ResizablePanel>
          </ResizablePanelGroup>
        ) : (
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <ChatPanel />
          </div>
        )}
      </div>
    </div>
  );
}
