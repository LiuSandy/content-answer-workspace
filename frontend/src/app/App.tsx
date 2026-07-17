import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { WorkspaceLayout } from "@/features/chat/workspace-shell";
import { ChatWorkspace } from "@/features/chat/chat-workspace";
import { HotlistPage } from "@/features/hotlist/hotlist-page";
import { SettingsPage } from "@/features/settings/settings-page";

/**
 * 应用路由根组件。
 *
 * 所有页面共享 WorkspaceLayout 的顶部 Header，主工作区和设置页通过 Outlet 切换。
 * hotlist 路由保留但不在导航中暴露（可通过 URL 直接访问）。
 */
export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<WorkspaceLayout />}>
          <Route index element={<ChatWorkspace />} />
          <Route path="chat/:chatId" element={<ChatWorkspace />} />
          <Route path="hotlist" element={<HotlistPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
