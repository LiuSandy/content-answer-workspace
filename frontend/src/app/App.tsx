import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { WorkspaceLayout } from "@/features/chat/workspace-shell";
import { ChatWorkspace } from "@/features/chat/chat-workspace";
import { SettingsPage } from "@/features/settings/settings-page";
import { KnowledgePage } from "@/features/knowledge/knowledge-page";

/**
 * 应用路由根组件。
 *
 * 所有页面共享 WorkspaceLayout 的顶部 Header，主工作区和设置页通过 Outlet 切换。
 */
export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<WorkspaceLayout />}>
          <Route index element={<ChatWorkspace />} />
          <Route path="chat/:chatId" element={<ChatWorkspace />} />
          <Route path="knowledge" element={<KnowledgePage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
