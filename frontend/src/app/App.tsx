import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { CollectPage, ImportPage, WorkspaceLayout } from "@/features/workspace/workspace-shell";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<WorkspaceLayout />}>
          <Route index element={<Navigate to="/import" replace />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="collect" element={<CollectPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/import" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
