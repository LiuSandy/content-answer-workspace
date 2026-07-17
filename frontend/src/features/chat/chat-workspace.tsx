import { useEffect } from "react";
import { useParams } from "react-router-dom";

import { ChatSidebar } from "./chat-sidebar";
import { ChatPanel } from "./chat-panel";
import { EditorPanel } from "./editor-panel";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { useChatStore } from "@/store/chat-store";

/**
 * Chat 主工作区三栏布局：侧边栏 + 对话 + 编辑面板。
 *
 * 独立组件（而非直接写在 WorkspaceLayout 里），因为其它路由（settings）
 * 不需要三栏结构，只需 WorkspaceLayout 的 Header + Outlet 外壳。
 */
export function ChatWorkspace() {
  const { chatId } = useParams<{ chatId: string }>();
  const { selectedSourceItemId, setCurrentChatId } = useChatStore();
  const showEditor = selectedSourceItemId !== null;

  useEffect(() => {
    setCurrentChatId(chatId || null);
  }, [chatId, setCurrentChatId]);

  return (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      <ChatSidebar />
      {showEditor ? (
        <ResizablePanelGroup orientation="horizontal" className="flex-1">
          <ResizablePanel defaultSize={50} minSize={30} className="flex flex-col min-h-0 overflow-hidden">
            <ChatPanel />
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize={50} minSize={30} className="flex flex-col min-h-0 overflow-hidden">
            <EditorPanel />
          </ResizablePanel>
        </ResizablePanelGroup>
      ) : (
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          <ChatPanel />
        </div>
      )}
    </div>
  );
}

