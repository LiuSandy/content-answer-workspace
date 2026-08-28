import { useState, useEffect, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Loader2, Save, AlertCircle, CheckCircle2 } from "lucide-react";
import { apiGet, apiPut } from "@/lib/api";
import { useAlertDialog } from "@/hooks/use-alert-dialog";

interface PromptTemplatesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type PromptData = {
  id: string;
  kind: "messages" | "fragment";
  systemPrompt: string;
  userPrompt: string;
  filePath: string;
};

/**
 * 提示词分层 Tab 配置。
 * 最终发给大模型的 system prompt = 通用原则 + 目标平台包 + 风格规则 + 字数约束，
 * 这里暴露前两层供用户编辑；新增平台包时在此追加一项即可，无需改其他代码。
 */
const PROMPT_TABS: Array<{ id: string; label: string; hint: string }> = [
  { id: "writing.answer_generate", label: "通用原则", hint: "所有平台共用的创作心智与避坑约束" },
  { id: "platform.zhihu", label: "知乎", hint: "知乎平台的格式规范、结构模式与雷区" },
  { id: "platform.xiaohongshu", label: "小红书", hint: "小红书平台的格式规范、结构模式与雷区" },
  { id: "platform.default", label: "其他平台", hint: "未单独适配平台的通用兜底规范" },
];

export function PromptTemplatesDialog({
  open,
  onOpenChange,
}: PromptTemplatesDialogProps) {
  const [activeTabId, setActiveTabId] = useState<string>(PROMPT_TABS[0].id);
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [systemPrompt, setSystemPrompt] = useState<string>("");
  const [loadedPrompt, setLoadedPrompt] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [successMsg, setSuccessMsg] = useState<string>("");
  const { confirm } = useAlertDialog();

  const isDirty = systemPrompt !== loadedPrompt;

  const fetchPrompt = useCallback(async (promptId: string) => {
    setLoading(true);
    setErrorMsg("");
    setSuccessMsg("");
    setSystemPrompt("");
    setLoadedPrompt("");
    try {
      const res = await apiGet<PromptData>(`/api/prompts/${promptId}`);
      setSystemPrompt(res.systemPrompt || "");
      setLoadedPrompt(res.systemPrompt || "");
    } catch (err: any) {
      console.error("Failed to load prompt template:", err);
      setErrorMsg(err.message || "拉取提示词模板失败，请检查后端服务。");
    } finally {
      setLoading(false);
    }
  }, []);

  // 弹窗打开时加载当前 Tab 对应的提示词
  useEffect(() => {
    if (!open) return;
    fetchPrompt(activeTabId);
  }, [open, activeTabId, fetchPrompt]);

  const handleSwitchTab = async (tabId: string) => {
    if (tabId === activeTabId) return;
    // 有未保存修改时切换需确认，防止误丢编辑内容
    if (isDirty) {
      const confirmed = await confirm("当前提示词有未保存的修改，切换后将丢失，确定切换吗？");
      if (!confirmed) return;
    }
    setActiveTabId(tabId);
  };

  const handleSave = async () => {
    setSaving(true);
    setErrorMsg("");
    setSuccessMsg("");
    try {
      await apiPut(`/api/prompts/${activeTabId}`, {
        systemPrompt,
        userPrompt: "",
      });
      setLoadedPrompt(systemPrompt);
      setSuccessMsg("提示词修改保存成功，已实时生效！");
      setTimeout(() => setSuccessMsg(""), 3000);
    } catch (err: any) {
      console.error("Failed to save prompt template:", err);
      setErrorMsg(err.message || "保存提示词失败。");
    } finally {
      setSaving(false);
    }
  };

  const activeTab = PROMPT_TABS.find((t) => t.id === activeTabId) ?? PROMPT_TABS[0];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl h-[80vh] flex flex-col p-6 overflow-hidden border-zinc-200 dark:border-zinc-800">
        {/* 用于隐藏编辑器滚动条轨道的内联样式 */}
        <style>{`
          .no-scrollbar::-webkit-scrollbar {
            display: none !important;
          }
        `}</style>

        <DialogHeader className="shrink-0">
          <DialogTitle className="text-lg font-bold">提示词管理</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground mt-1">
            最终提示词按「通用原则 + 目标平台包 + 风格规则 + 字数约束」分层拼接；此处编辑前两层。
          </DialogDescription>
        </DialogHeader>

        {/* ── 分层 Tab 切换 ── */}
        <div className="shrink-0 mt-3 flex items-center gap-1.5 border-b border-zinc-200 dark:border-zinc-800 pb-2">
          {PROMPT_TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleSwitchTab(tab.id)}
              disabled={saving || loading}
              className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
                tab.id === activeTabId
                  ? "bg-indigo-600 text-white font-semibold"
                  : "text-muted-foreground hover:bg-zinc-100 dark:hover:bg-zinc-800"
              }`}
            >
              {tab.label}
            </button>
          ))}
          <span className="ml-2 text-[10px] text-muted-foreground truncate">
            {activeTab.hint}
          </span>
        </div>

        <div className="flex-1 min-h-0 relative flex flex-col mt-3">
          {loading ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-background/50">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
              <span className="text-xs text-muted-foreground">正在加载模板内容...</span>
            </div>
          ) : (
            <div className="flex flex-col flex-1 min-h-0 space-y-4">
              {/* 错误提示 */}
              {errorMsg && (
                <div className="flex items-start gap-2.5 rounded-xl border border-red-100 bg-red-50/50 p-4 dark:border-red-950/40 dark:bg-red-950/10 text-red-600 dark:text-red-400 text-xs leading-relaxed shrink-0 max-h-[90px] overflow-y-auto">
                  <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                  <div className="flex-1 font-medium whitespace-pre-wrap">{errorMsg}</div>
                </div>
              )}

              {/* 成功提示 */}
              {successMsg && (
                <div className="flex items-center gap-2.5 rounded-xl border border-green-100 bg-green-50/50 p-4 dark:border-green-950/40 dark:bg-green-950/10 text-green-600 dark:text-green-400 text-xs font-semibold shrink-0">
                  <CheckCircle2 className="h-4 w-4 shrink-0" />
                  <span>{successMsg}</span>
                </div>
              )}

              {/* 编辑区 */}
              <div className="flex-1 min-h-0 flex flex-col">
                <div className="flex-1 flex flex-col min-h-0">
                  <div className="flex-1 min-h-0 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-950 p-4 flex flex-col">
                    <textarea
                      value={systemPrompt}
                      onChange={(e) => setSystemPrompt(e.target.value)}
                      disabled={saving}
                      className="w-full flex-1 bg-transparent resize-none border-0 text-zinc-100 font-mono text-xs leading-relaxed outline-none focus:outline-none focus:ring-0 overflow-y-auto no-scrollbar"
                      style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
                      placeholder="输入提示词内容..."
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="shrink-0 border-t pt-4 mt-4 gap-2 flex items-center justify-end">
          {isDirty && !saving && (
            <span className="mr-auto text-[10px] text-amber-600 dark:text-amber-400">
              有未保存的修改
            </span>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={saving}
            className="text-xs"
          >
            取消
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={loading || saving || !(systemPrompt || "").trim() || !isDirty}
            className="text-xs gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            {saving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="h-3.5 w-3.5" />
            )}
            {saving ? "正在校验并保存..." : "保存并生效"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
