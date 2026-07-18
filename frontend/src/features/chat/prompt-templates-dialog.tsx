import { useState, useEffect } from "react";
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

interface PromptTemplatesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type PromptData = {
  id: string;
  systemPrompt: string;
  userPrompt: string;
  filePath: string;
};

export function PromptTemplatesDialog({
  open,
  onOpenChange,
}: PromptTemplatesDialogProps) {
  const promptId = "writing.answer_generate";
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [systemPrompt, setSystemPrompt] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [successMsg, setSuccessMsg] = useState<string>("");

  // 当弹窗打开时，从后端拉取系统提示词内容
  useEffect(() => {
    if (!open) return;

    const fetchPrompt = async () => {
      setLoading(true);
      setErrorMsg("");
      setSuccessMsg("");
      setSystemPrompt("");
      try {
        const res = await apiGet<PromptData>(
          `/api/prompts/${promptId}`
        );
        setSystemPrompt(res.systemPrompt || "");
      } catch (err: any) {
        console.error("Failed to load prompt template:", err);
        setErrorMsg(err.message || "拉取提示词模板失败，请检查后端服务。");
      } finally {
        setLoading(false);
      }
    };

    fetchPrompt();
  }, [open]);

  const handleSave = async () => {
    setSaving(true);
    setErrorMsg("");
    setSuccessMsg("");
    try {
      await apiPut(`/api/prompts/${promptId}`, {
        systemPrompt,
        userPrompt: "",
      });
      setSuccessMsg("提示词修改保存成功，已实时生效！");
      setTimeout(() => setSuccessMsg(""), 3000);
    } catch (err: any) {
      console.error("Failed to save prompt template:", err);
      setErrorMsg(err.message || "保存提示词失败。");
    } finally {
      setSaving(false);
    }
  };

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
            编辑 AI 创作所使用的核心系统提示词 (System Prompt) 模板文本。
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 min-h-0 relative flex flex-col mt-4">
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
                {/* 系统提示词 */}
                <div className="flex-1 flex flex-col min-h-0">
                  <div className="flex-1 min-h-0 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-950 p-4 flex flex-col">
                    <textarea
                      value={systemPrompt}
                      onChange={(e) => setSystemPrompt(e.target.value)}
                      disabled={saving}
                      className="w-full flex-1 bg-transparent resize-none border-0 text-zinc-100 font-mono text-xs leading-relaxed outline-none focus:outline-none focus:ring-0 overflow-y-auto no-scrollbar"
                      style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
                      placeholder="输入系统提示词模板..."
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="shrink-0 border-t pt-4 mt-4 gap-2 flex items-center justify-end">
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
            disabled={loading || saving || !(systemPrompt || "").trim()}
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
