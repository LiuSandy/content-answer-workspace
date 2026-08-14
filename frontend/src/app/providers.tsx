import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type PropsWithChildren } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { AlertDialogProvider } from "@/hooks/use-alert-dialog";

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      {/* 全局挂载 TooltipProvider：各处 Tooltip 依赖单一 Provider 上下文，避免每个组件重复包裹 */}
      <TooltipProvider delayDuration={200}>
        {/* 全局挂载 AlertDialogProvider：统一替代原生 alert()/confirm()，全站唯一入口 */}
        <AlertDialogProvider>{children}</AlertDialogProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}
