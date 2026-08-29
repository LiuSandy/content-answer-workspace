/**
 * Agent-Reach 平台配置分区；展示各平台健康状态、启用开关和安装引导，
 * 因为「是否可用」和「如何配置」需要联合展示才能让用户知道下一步该怎么做。
 */

import { useCallback, useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  useAgentReachStatus,
  useConfigureGroqKey,
  useSaveTwitterAuth,
  useSettings,
  useTwitterAuth,
  useUpdateAgentReachPlatforms,
} from "./use-settings";

interface PlatformMeta {
  name: string;
  desc: string;
  setupType: "zero-config" | "install-package" | "install-cli" | "requires-auth";
  setupSteps: Array<{ label: string; code?: string }>;
}

const PLATFORM_META: Record<string, PlatformMeta> = {
  v2ex: {
    name: "V2EX",
    desc: "热门话题 + 节点帖",
    setupType: "zero-config",
    setupSteps: [{ label: "无需任何配置，使用 V2EX 公开 JSON API" }],
  },
  reddit: {
    name: "Reddit",
    desc: "帖子搜索 + 评论",
    setupType: "zero-config",
    setupSteps: [{ label: "无需任何配置，使用 Reddit 公开 JSON API" }],
  },
  rss: {
    name: "RSS",
    desc: "RSS/Atom 订阅源解析",
    setupType: "install-package",
    setupSteps: [
      { label: "安装 feedparser 包", code: "uv add feedparser" },
      { label: "重启后端使依赖生效" },
    ],
  },
  github: {
    name: "GitHub",
    desc: "仓库搜索 + 详情",
    setupType: "install-cli",
    setupSteps: [
      { label: "安装 GitHub CLI", code: "brew install gh" },
      { label: "（可选）登录以提升 API 限额", code: "gh auth login" },
      { label: "公开仓库搜索无需登录" },
    ],
  },
  youtube: {
    name: "YouTube",
    desc: "字幕 + 视频信息",
    setupType: "install-cli",
    setupSteps: [
      { label: "安装 yt-dlp", code: "brew install yt-dlp" },
      { label: "或通过 pip 安装", code: "pip install yt-dlp" },
      { label: "验证安装", code: "yt-dlp --version" },
    ],
  },
  bilibili: {
    name: "B 站",
    desc: "视频搜索 + 详情",
    setupType: "install-cli",
    setupSteps: [
      { label: "安装 bili-cli（第三方工具）", code: "npm install -g bili-cli" },
      { label: "验证安装", code: "bili --version" },
      { label: "部分功能需要登录 B 站账号" },
    ],
  },
  twitter: {
    name: "Twitter/X",
    desc: "推文读取 + 搜索",
    setupType: "requires-auth",
    setupSteps: [],
  },
  xiaohongshu: {
    name: "小红书",
    desc: "笔记搜索 + 正文",
    setupType: "requires-auth",
    setupSteps: [],
  },
};

const SETUP_TYPE_BADGE: Record<PlatformMeta["setupType"], { label: string; className: string }> = {
  "zero-config": { label: "零配置", className: "bg-green-50 text-green-700 border-green-200" },
  "install-package": { label: "装包即用", className: "bg-blue-50 text-blue-700 border-blue-200" },
  "install-cli": { label: "装 CLI", className: "bg-sky-50 text-sky-700 border-sky-200" },
  "requires-auth": {
    label: "需要认证",
    className: "bg-orange-50 text-orange-700 border-orange-200",
  },
};

function SetupGuide({ steps }: { steps: PlatformMeta["setupSteps"] }) {
  return (
    <div className="mt-2 ml-1 space-y-1.5 border-l-2 border-muted pl-3">
      {steps.map((step, i) => (
        <div key={i} className="space-y-0.5">
          <p className="text-[11px] text-muted-foreground">{step.label}</p>
          {step.code && (
            <code className="block text-[11px] font-mono bg-muted px-2 py-0.5 rounded select-all">
              {step.code}
            </code>
          )}
        </div>
      ))}
    </div>
  );
}

function TwitterAuthInput() {
  const { data: auth } = useTwitterAuth();
  const [authToken, setAuthToken] = useState("");
  const [ct0, setCt0] = useState("");
  const [saved, setSaved] = useState(false);
  const save = useSaveTwitterAuth();

  async function handleSave() {
    await save.mutateAsync({ authToken, ct0 });
    setAuthToken("");
    setCt0("");
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="mt-2 ml-1 space-y-2 border-l-2 border-muted pl-3">
      <p className="text-[11px] text-muted-foreground">
        在浏览器中登录 Twitter/X，打开开发者工具（F12）→ Application → Cookies → 找到{" "}
        <code className="bg-muted px-1 rounded">auth_token</code> 和{" "}
        <code className="bg-muted px-1 rounded">ct0</code> 两个字段。
      </p>
      <div className="flex items-center gap-1.5 text-[11px]">
        <span className="text-muted-foreground">当前状态：</span>
        {auth?.configured ? (
          <span className="text-green-600 font-medium">已配置 ✓</span>
        ) : (
          <span className="text-orange-600">未配置</span>
        )}
      </div>
      <div className="space-y-1.5">
        <Input
          value={authToken}
          onChange={(e) => setAuthToken(e.target.value)}
          placeholder={auth?.authToken ?? "auth_token 值"}
          className="font-mono text-[11px] h-7"
        />
        <Input
          value={ct0}
          onChange={(e) => setCt0(e.target.value)}
          placeholder={auth?.ct0 ?? "ct0 值"}
          className="font-mono text-[11px] h-7"
        />
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={handleSave} disabled={save.isPending || (!authToken && !ct0)}>
          {save.isPending ? "保存中…" : "保存"}
        </Button>
        {saved && <span className="text-[11px] text-green-600">已保存，重启后端生效 ✓</span>}
      </div>
    </div>
  );
}

function OpenCliGuide({ platform }: { platform: string }) {
  return (
    <div className="mt-2 ml-1 space-y-1.5 border-l-2 border-muted pl-3">
      <p className="text-[11px] text-muted-foreground">
        通过 OpenCLI 复用 Chrome 浏览器登录态，无需手动导出 Cookie。
      </p>
      <div className="space-y-0.5">
        <p className="text-[11px] text-muted-foreground">① 安装 OpenCLI Chrome 扩展</p>
        <code className="block text-[11px] font-mono bg-muted px-2 py-0.5 rounded select-all">
          https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk
        </code>
      </div>
      <p className="text-[11px] text-muted-foreground">
        ② 在 Chrome 中登录{platform === "xiaohongshu" ? "小红书" : "Reddit"}，保持 Chrome
        开启即可使用。
      </p>
    </div>
  );
}

export function AgentReachSettings() {
  const { data: settings } = useSettings();
  const { data: status, refetch, isFetching } = useAgentReachStatus();
  const updatePlatforms = useUpdateAgentReachPlatforms();
  const configureGroq = useConfigureGroqKey();

  const [expandedPlatforms, setExpandedPlatforms] = useState<Set<string>>(new Set());
  const [groqKey, setGroqKey] = useState("");
  const [groqSaved, setGroqSaved] = useState(false);

  const enabledPlatforms = settings?.agentReach.enabledPlatforms ?? [];

  function toggleExpand(platform: string) {
    setExpandedPlatforms((prev) => {
      const next = new Set(prev);
      if (next.has(platform)) {
        next.delete(platform);
      } else {
        next.add(platform);
      }
      return next;
    });
  }

  const handleToggle = useCallback(
    async (platform: string, enabled: boolean) => {
      const next = enabled
        ? [...enabledPlatforms, platform]
        : enabledPlatforms.filter((p) => p !== platform);
      await updatePlatforms.mutateAsync(next);
    },
    [enabledPlatforms, updatePlatforms],
  );

  async function handleSaveGroqKey() {
    await configureGroq.mutateAsync(groqKey);
    setGroqKey("");
    setGroqSaved(true);
    setTimeout(() => setGroqSaved(false), 2000);
  }

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium">平台状态</h3>
          <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} />
            刷新诊断
          </Button>
        </div>

        <div className="rounded-lg border divide-y">
          {Object.entries(PLATFORM_META).map(([platform, meta]) => {
            const isEnabled = enabledPlatforms.includes(platform);
            const isExpanded = expandedPlatforms.has(platform);
            const platformStatus = status?.data
              ? (status.data as Record<string, { healthy?: boolean; error?: string }>)[platform]
              : null;
            const setupBadge = SETUP_TYPE_BADGE[meta.setupType];

            return (
              <div key={platform} className="px-4 py-3">
                <div className="flex items-start gap-3">
                  {/* 展开按钮 */}
                  <button
                    type="button"
                    onClick={() => toggleExpand(platform)}
                    className="mt-0.5 shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                    aria-label={isExpanded ? "收起配置引导" : "展开配置引导"}
                  >
                    {isExpanded ? (
                      <ChevronDown className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5" />
                    )}
                  </button>

                  {/* 平台信息 */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium">{meta.name}</span>
                      {/* 配置难度徽章 */}
                      <Badge
                        variant="secondary"
                        className={`text-[10px] h-4 px-1.5 ${setupBadge.className}`}
                      >
                        {setupBadge.label}
                      </Badge>
                      {/* 运行时健康状态（来自 agent-reach doctor） */}
                      {platformStatus?.healthy === true && (
                        <Badge
                          variant="secondary"
                          className="text-[10px] h-4 px-1.5 bg-green-50 text-green-700 border-green-200"
                        >
                          已就绪
                        </Badge>
                      )}
                      {platformStatus?.healthy === false && (
                        <Badge
                          variant="secondary"
                          className="text-[10px] h-4 px-1.5 bg-red-50 text-red-700 border-red-200"
                        >
                          未就绪
                        </Badge>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5">{meta.desc}</p>
                    {platformStatus?.error && (
                      <p className="text-[11px] text-red-600 mt-0.5">{platformStatus.error}</p>
                    )}

                    {/* 配置引导（展开后显示） */}
                    {isExpanded && platform === "twitter" ? (
                      <TwitterAuthInput />
                    ) : isExpanded && (platform === "xiaohongshu" || platform === "reddit") ? (
                      <OpenCliGuide platform={platform} />
                    ) : isExpanded && meta.setupSteps.length > 0 ? (
                      <SetupGuide steps={meta.setupSteps} />
                    ) : null}
                  </div>

                  {/* 启用开关 */}
                  <Switch
                    checked={isEnabled}
                    onCheckedChange={(v) => handleToggle(platform, v)}
                    disabled={updatePlatforms.isPending}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {status && !status.ok && (
          <p className="text-xs text-amber-600 bg-amber-50 rounded px-3 py-2 border border-amber-200">
            {status.error ?? "agent-reach doctor 执行失败，健康状态无法获取"}
          </p>
        )}
      </div>

      {/* Groq Key 配置 */}
      <div className="space-y-2 border-t pt-5">
        <Label>Groq API Key</Label>
        <div className="flex gap-2">
          <Input
            type="password"
            value={groqKey}
            onChange={(e) => setGroqKey(e.target.value)}
            placeholder={settings?.agentReach.groqApiKey ?? "留空则不更新"}
            className="font-mono text-sm flex-1"
          />
          <Button onClick={handleSaveGroqKey} disabled={configureGroq.isPending || !groqKey}>
            保存
          </Button>
        </div>
        {groqSaved && <span className="text-sm text-green-600">已保存 ✓</span>}
        <p className="text-[11px] text-muted-foreground">
          Groq 提供免费 tier，用于部分 Agent-Reach 平台的 AI 摘要功能。
        </p>
      </div>

      <p className="text-xs text-amber-600 bg-amber-50 rounded-md px-3 py-2 border border-amber-200">
        ⚠️ 平台开关变更后需点击「重启后端」使 ALL_TOOLS 重新加载。
      </p>
    </div>
  );
}
