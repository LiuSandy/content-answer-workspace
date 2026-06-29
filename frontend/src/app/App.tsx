import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { ChatPage } from "@/features/workspace/chat-page";
import { CollectPage, HotlistPage, ImportPage, WorkspaceLayout } from "@/features/workspace/workspace-shell";
import { WorkbenchPage } from "@/features/workbench/workbench-page";
import { SettingsPage } from "@/features/settings/settings-page";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<WorkspaceLayout />}>
          <Route index element={<Navigate to="/import" replace />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="collect" element={<CollectPage />} />
          <Route path="hotlist" element={<HotlistPage />} />
          <Route path="workbench" element={<WorkbenchPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/import" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
