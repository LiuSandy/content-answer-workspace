import { useState, useEffect } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { BrainCircuit, Settings, Moon, Sun, SearchCode } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { PromptTemplatesDialog } from "@/features/chat/prompts/prompt-templates-dialog";
import { RagSearchTestDialog } from "@/features/knowledge/rag-search-test-dialog";

/**
 * 应用外壳：顶部 Header + 主体 Outlet。
 *
 * 完全按照设计稿 docs/private-knowledge-rag-ui.html 落地顶栏：
 * 包含品牌 Logo、顶部路由切签 Tabs (创作工作台 / 私有资料库) 与设置/主题切换。
 */
export function WorkspaceLayout() {
  const location = useLocation();
  const [darkMode, setDarkMode] = useState(false);
  const [isPromptDialogOpen, setIsPromptDialogOpen] = useState(false);
  const [isRagTestOpen, setIsRagTestOpen] = useState(false);

  useEffect(() => {
    setDarkMode(document.documentElement.classList.contains("dark"));
  }, []);

  const toggleDarkMode = () => {
    const nextDark = !darkMode;
    setDarkMode(nextDark);
    document.documentElement.classList.toggle("dark", nextDark);
  };

  const isKnowledgePage = location.pathname.startsWith("/knowledge");

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      {/* ── 100% 对齐设计稿的 56px 顶部 Header ── */}
      <header className="flex h-[56px] shrink-0 items-center border-b bg-card px-4 gap-6">
        {/* 品牌区 (.kb-brand) */}
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-tr from-indigo-500 to-purple-600 shadow-sm">
            <BrainCircuit className="h-5 w-5 text-white" />
          </div>
          <span className="text-base font-bold tracking-tight">超级大脑</span>
        </Link>

        {/* 顶部路由切签导航 (.kb-nav) */}
        <nav className="self-stretch flex items-center gap-1.5 ml-3.5">
          <Link
            to="/"
            className={`h-full flex items-center px-3.25 text-xs font-semibold border-b-2 transition-colors ${
              !isKnowledgePage
                ? "text-foreground border-[#334155] dark:border-primary font-bold"
                : "text-muted-foreground border-transparent hover:text-foreground"
            }`}
          >
            创作工作台
          </Link>
          <Link
            to="/knowledge"
            className={`h-full flex items-center px-3.25 text-xs font-semibold border-b-2 transition-colors ${
              isKnowledgePage
                ? "text-foreground border-[#334155] dark:border-primary font-bold"
                : "text-muted-foreground border-transparent hover:text-foreground"
            }`}
          >
            私有资料库
          </Link>
        </nav>

        {/* 右侧操作区 (.kb-actions) */}
        <div className="ml-auto flex items-center gap-2">
          {/* 在“提示词”按钮左侧放置 RAG 检索测试按钮 */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsRagTestOpen(true)}
            className="h-8 gap-1.5 text-xs font-semibold px-3 border-indigo-500/30 hover:border-indigo-500 hover:bg-indigo-50/50 dark:hover:bg-indigo-950/30"
          >
            <SearchCode className="h-3.5 w-3.5 text-indigo-500" />
            RAG 测试
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsPromptDialogOpen(true)}
            className="h-8 gap-1.5 text-xs font-semibold px-3"
          >
            <Settings className="h-3.5 w-3.5" />
            提示词
          </Button>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" onClick={toggleDarkMode} className="h-8 w-8">
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

      {/* ── RAG 检索测试弹窗 ── */}
      <RagSearchTestDialog open={isRagTestOpen} onOpenChange={setIsRagTestOpen} />

      {/* ── 提示词模板管理弹窗 ── */}
      <PromptTemplatesDialog open={isPromptDialogOpen} onOpenChange={setIsPromptDialogOpen} />
    </div>
  );
}
