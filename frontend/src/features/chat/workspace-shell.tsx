import { useState, useEffect } from "react";
import { Link, Outlet } from "react-router-dom";
import { BrainCircuit, Settings, Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { PromptTemplatesDialog } from "./prompt-templates-dialog";

/**
 * 应用外壳：顶部 Header + 主体 Outlet。
 *
 * 按设计稿采用「顶部导航栏 + 三栏工作台」布局，取代旧的左侧图标导航栏，
 * 因为 Chat-first 场景只需要一个全局品牌区和设置入口，导航层级越少越沉浸。
 */
export function WorkspaceLayout() {
  const [darkMode, setDarkMode] = useState(false);
  const [isPromptDialogOpen, setIsPromptDialogOpen] = useState(false);

  // 初始化深色模式状态：读取 <html> 上已有的 class，保持刷新后一致
  useEffect(() => {
    setDarkMode(document.documentElement.classList.contains("dark"));
  }, []);

  const toggleDarkMode = () => {
    const nextDark = !darkMode;
    setDarkMode(nextDark);
    document.documentElement.classList.toggle("dark", nextDark);
  };

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      {/* ── 顶部 Header ── */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b bg-card px-4">
        {/* 品牌区 */}
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-tr from-indigo-500 to-purple-600 shadow-sm">
            <BrainCircuit className="h-5 w-5 text-white" />
          </div>
          <span className="text-base font-bold tracking-tight">超级大脑</span>
        </Link>

        {/* 右侧操作区 */}
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setIsPromptDialogOpen(true)}>
            <Settings className="h-4 w-4" />
            提示词
          </Button>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" onClick={toggleDarkMode}>
                {darkMode ? (
                  <Sun className="h-4 w-4 text-amber-400" />
                ) : (
                  <Moon className="h-4 w-4" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>切换深色 / 浅色模式</TooltipContent>
          </Tooltip>
        </div>
      </header>

      {/* ── 主体内容区 ── */}
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>

      {/* ── 提示词模板管理弹窗 ── */}
      <PromptTemplatesDialog
        open={isPromptDialogOpen}
        onOpenChange={setIsPromptDialogOpen}
      />
    </div>
  );
}
