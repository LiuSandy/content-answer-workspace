import { ChatSidebar } from "./chat-sidebar";
import { ChatPanel } from "./chat-panel";
import { EditorPanel } from "./editor-panel";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";

/**
 * Chat 主工作区三栏布局：侧边栏 + 对话 + 编辑面板。
 *
 * 独立组件（而非直接写在 WorkspaceLayout 里），因为其它路由（settings）
 * 不需要三栏结构，只需 WorkspaceLayout 的 Header + Outlet 外壳。
 */
export function ChatWorkspace() {
  return (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      <ChatSidebar />
      <ResizablePanelGroup orientation="horizontal" className="flex-1">
        <ResizablePanel defaultSize={50} minSize={30} className="flex flex-col min-h-0 overflow-hidden">
          <ChatPanel />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize={50} minSize={30} className="flex flex-col min-h-0 overflow-hidden">
          <EditorPanel />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}

