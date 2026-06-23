/**
 * 设置页主组件；提供两列布局（左侧导航 + 右侧内容区）和顶部重启按钮，
 * 因为所有配置分区共用同一个重启入口和布局骨架。
 */

import { useCallback, useRef, useState } from "react";
import { RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { checkHealth, restartServer } from "./settings-api";
import { AgentReachSettings } from "./agent-reach-settings";
import { CollectSettings } from "./collect-settings";
import { LlmSettings } from "./llm-settings";
import { PromptsSettings } from "./prompts-settings";
import { PublishSettings } from "./publish-settings";
import { TopicsSettings } from "./topics-settings";

type Section = "llm" | "agent-reach" | "topics" | "publish" | "collect" | "prompts";

interface NavItem {
  id: Section;
  label: string;
  description: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: "llm", label: "LLM 配置", description: "Base URL、模型、API Key" },
  { id: "agent-reach", label: "Agent-Reach", description: "平台工具开关与诊断" },
  { id: "topics", label: "主题管理", description: "采集主题的增删改" },
  { id: "publish", label: "发布配置", description: "测试模式与 CTA 文本" },
  { id: "collect", label: "采集默认值", description: "平台、上限、排序模式" },
  { id: "prompts", label: "默认提示词", description: "全局 System Prompt" },
];

const SECTION_COMPONENTS: Record<Section, React.FC> = {
  llm: LlmSettings,
  "agent-reach": AgentReachSettings,
  topics: TopicsSettings,
  publish: PublishSettings,
  collect: CollectSettings,
  prompts: PromptsSettings,
};

type RestartState = "idle" | "pending" | "polling" | "success" | "error";

export function SettingsPage() {
  const [activeSection, setActiveSection] = useState<Section>("llm");
  const [restartState, setRestartState] = useState<RestartState>("idle");
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const handleRestart = useCallback(async () => {
    if (restartState === "pending" || restartState === "polling") return;
    setRestartState("pending");

    await restartServer();
    setRestartState("polling");

    let attempts = 0;
    pollingRef.current = setInterval(async () => {
      attempts++;
      const ok = await checkHealth();
      if (ok) {
        stopPolling();
        setRestartState("success");
        setTimeout(() => setRestartState("idle"), 3000);
      } else if (attempts >= 30) {
        // 15 秒超时
        stopPolling();
        setRestartState("error");
        setTimeout(() => setRestartState("idle"), 5000);
      }
    }, 500);
  }, [restartState, stopPolling]);

  const ActiveSection = SECTION_COMPONENTS[activeSection];
  const activeNav = NAV_ITEMS.find((n) => n.id === activeSection)!;

  return (
    <section className="flex flex-1 flex-col min-h-0">
      {/* ── 顶部 bar ── */}
      <div className="flex items-center justify-between h-12 px-6 border-b shrink-0">
        <h1 className="text-sm font-semibold">设置</h1>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRestart}
          disabled={restartState === "pending" || restartState === "polling"}
          className={
            restartState === "idle"
              ? "border-amber-300 text-amber-700 hover:bg-amber-50"
              : restartState === "success"
              ? "border-green-300 text-green-700"
              : restartState === "error"
              ? "border-red-300 text-red-700"
              : "border-amber-300 text-amber-700 opacity-60"
          }
        >
          <RotateCw
            className={`h-3.5 w-3.5 mr-1.5 ${
              restartState === "pending" || restartState === "polling" ? "animate-spin" : ""
            }`}
          />
          {restartState === "idle" && "重启后端"}
          {restartState === "pending" && "重启中…"}
          {restartState === "polling" && "等待启动…"}
          {restartState === "success" && "重启成功 ✓"}
          {restartState === "error" && "重启超时，请手动检查"}
        </Button>
      </div>

      {/* ── 两列主体 ── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* 左侧导航 */}
        <nav className="w-52 shrink-0 border-r overflow-y-auto py-3">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setActiveSection(item.id)}
              className={`w-full text-left px-4 py-2.5 transition-colors ${
                activeSection === item.id
                  ? "bg-muted text-foreground font-medium"
                  : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
              }`}
            >
              <p className="text-sm">{item.label}</p>
              <p className="text-[10px] mt-0.5 opacity-70 leading-tight">{item.description}</p>
            </button>
          ))}
        </nav>

        {/* 右侧内容区 */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-2xl px-8 py-6">
            <div className="mb-5">
              <h2 className="text-base font-semibold">{activeNav.label}</h2>
              <p className="text-xs text-muted-foreground mt-0.5">{activeNav.description}</p>
            </div>
            <Separator className="mb-5" />
            <ActiveSection />
          </div>
        </div>
      </div>
    </section>
  );
}
