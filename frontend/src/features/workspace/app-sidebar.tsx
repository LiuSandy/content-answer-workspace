import { useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Layers, MessageSquare, Plus, Sparkles, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarSeparator,
} from "@/components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/store/workspace-store";
import { createSession, deleteSession, listSessions } from "./workflow-api";

const SESSION_LIST_QUERY_KEY = ["chat-session-list"];

const navItems = [
  { to: "/import", label: "URL 导入回答", icon: ArrowUpRight },
  { to: "/collect", label: "主题采集", icon: Layers },
  { to: "/hotlist", label: "知乎热榜", icon: Sparkles },
  { to: "/chat", label: "对话", icon: MessageSquare },
] as const;

export function AppSidebar() {
  const location = useLocation();
  const activeSessionId = useWorkspaceStore((s) => s.activeSessionId);
  const setActiveSessionId = useWorkspaceStore((s) => s.setActiveSessionId);
  const [isCreating, setIsCreating] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data: sessions = [] } = useQuery({
    queryKey: SESSION_LIST_QUERY_KEY,
    queryFn: listSessions,
  });

  async function handleCreateSession() {
    if (isCreating) return;
    setIsCreating(true);
    try {
      const session = await createSession();
      setActiveSessionId(session.sessionId);
      queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
      navigate("/chat");
    } finally {
      setIsCreating(false);
    }
  }

  async function handleDeleteSession(sessionId: string) {
    await deleteSession(sessionId);
    if (activeSessionId === sessionId) {
      setActiveSessionId(null);
    }
    queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
  }

  return (
    <Sidebar collapsible="icon">
      {/* ── Logo ── */}
      <SidebarHeader className="h-12 flex items-center border-b border-sidebar-border px-3">
        <div className="flex items-center gap-2 w-full">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] bg-slate-900 text-[10px] font-bold tracking-tight text-white">
            CW
          </div>
          <div className="flex-1 overflow-hidden leading-none group-data-[collapsible=icon]:hidden">
            <div className="truncate text-[13px] font-semibold text-slate-900">内容工作台</div>
            <div className="mt-[1px] truncate text-[10px] font-medium text-slate-400">Content Workspace</div>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent className="overflow-x-hidden">
        {/* ── 导航菜单 ── */}
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map(({ to, label, icon: Icon }) => {
                const isActive =
                  location.pathname === to ||
                  location.pathname.startsWith(to + "/");
                return (
                  <SidebarMenuItem key={to}>
                    <SidebarMenuButton asChild tooltip={label} isActive={isActive}>
                      <NavLink to={to} end>
                        <Icon />
                        <span>{label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator />

        {/* ── 对话历史（折叠模式下整组隐藏） ── */}
        <SidebarGroup className="group-data-[collapsible=icon]:hidden">
          <div className="flex items-center justify-between px-2 py-1">
            <SidebarGroupLabel className="p-0 text-[11px]">对话历史</SidebarGroupLabel>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5 text-muted-foreground hover:text-foreground hover:bg-sidebar-accent"
                  onClick={handleCreateSession}
                  disabled={isCreating}
                >
                  <Plus className="h-3.5 w-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">新建对话</TooltipContent>
            </Tooltip>
          </div>

          <SidebarGroupContent>
            <ScrollArea className="max-h-[300px]">
              <SidebarMenu>
                {sessions.length === 0 ? (
                  <p className="px-2 py-2 text-[11px] text-muted-foreground">
                    还没有对话，点击 + 新建。
                  </p>
                ) : (
                  sessions.map((session) => (
                    <SidebarMenuItem key={session.sessionId}>
                      <div
                        className={cn(
                          "group/item flex w-full min-w-0 items-center gap-1 rounded-md px-2 py-1.5 transition-colors hover:bg-sidebar-accent",
                          session.sessionId === activeSessionId && "bg-sidebar-accent font-medium",
                        )}
                      >
                        <button
                          type="button"
                          className="min-w-0 flex-1 truncate text-left text-[12px]"
                          onClick={() => {
                            setActiveSessionId(session.sessionId);
                            navigate("/chat");
                          }}
                        >
                          {session.title}
                        </button>
                        <button
                          type="button"
                          className="invisible shrink-0 rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover/item:visible group-hover/item:opacity-100"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteSession(session.sessionId);
                          }}
                          aria-label="删除对话"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </SidebarMenuItem>
                  ))
                )}
              </SidebarMenu>
            </ScrollArea>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter />
      <SidebarRail />
    </Sidebar>
  );
}
