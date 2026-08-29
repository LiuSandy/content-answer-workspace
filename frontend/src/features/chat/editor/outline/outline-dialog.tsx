import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  HelpCircle,
  History,
  ListTree,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  addKeyPoint,
  addSection,
  removeKeyPoint,
  removeSection,
  updateSection,
  type EditableOutlineSection,
} from "./outline-editor";
import { outlineDialogLayout } from "./outline-dialog-layout";

interface OutlineData {
  operationId?: string;
  versionNumber: number;
  basedOnOperationId?: string | null;
  status: "draft" | "confirmed";
  viewpointQuestions: string[] | null;
  outline: EditableOutlineSection[];
}

interface OutlineDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentId: string | null;
  sourceItemId: string | null;
  lockVersion: number;
  onLockConflict?: () => void;
}

async function unwrapOutline(response: Response, fallback: string): Promise<OutlineData> {
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload?.error || fallback) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return payload.data as OutlineData;
}

async function getOutline(documentId: string): Promise<OutlineData | null> {
  const response = await fetch(`/api/documents/${documentId}/outline/current`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.error || "加载大纲失败");
  return payload.data;
}

async function getOutlineVersions(documentId: string): Promise<OutlineData[]> {
  const response = await fetch(`/api/documents/${documentId}/outline/versions`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.error || "加载大纲历史失败");
  return payload.data;
}

async function activateOutlineVersion(
  documentId: string,
  operationId: string,
  lockVersion: number,
): Promise<OutlineData> {
  const response = await fetch(
    `/api/documents/${documentId}/outline/versions/${operationId}/activate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expectedLockVersion: lockVersion }),
    },
  );
  return unwrapOutline(response, "切换大纲版本失败");
}

async function generateOutline(
  documentId: string,
  sourceItemId: string,
  lockVersion: number,
  regenerate: boolean,
): Promise<OutlineData> {
  const action = regenerate ? "regenerate" : "generate";
  const response = await fetch(`/api/documents/${documentId}/outline/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sourceItemId, expectedLockVersion: lockVersion }),
  });
  return unwrapOutline(response, regenerate ? "重新生成大纲失败" : "生成大纲失败");
}

async function updateOutline(
  documentId: string,
  sections: EditableOutlineSection[],
  viewpointAnswers: Record<string, string>,
  lockVersion: number,
): Promise<OutlineData> {
  const response = await fetch(`/api/documents/${documentId}/outline/update`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sections: sections.map((section, index) => ({ ...section, order: index + 1 })),
      viewpointAnswers,
      expectedLockVersion: lockVersion,
    }),
  });
  return unwrapOutline(response, "保存大纲失败");
}

async function confirmOutline(documentId: string, lockVersion: number): Promise<OutlineData> {
  const response = await fetch(`/api/documents/${documentId}/outline/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expectedLockVersion: lockVersion }),
  });
  return unwrapOutline(response, "确认大纲失败");
}

export function OutlineDialog({
  open,
  onOpenChange,
  documentId,
  sourceItemId,
  lockVersion,
  onLockConflict,
}: OutlineDialogProps) {
  const queryClient = useQueryClient();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [sections, setSections] = useState<EditableOutlineSection[]>([]);
  const [editing, setEditing] = useState(false);

  const { data: outline, isLoading } = useQuery<OutlineData | null>({
    queryKey: ["outline", documentId],
    queryFn: () => (documentId ? getOutline(documentId) : null),
    enabled: open && !!documentId,
  });
  const { data: versions = [] } = useQuery<OutlineData[]>({
    queryKey: ["outline-versions", documentId],
    queryFn: () => (documentId ? getOutlineVersions(documentId) : []),
    enabled: open && !!documentId,
  });

  useEffect(() => {
    if (!open) return;
    setSections(outline?.outline ?? []);
    setEditing(outline?.status === "draft");
  }, [open, outline]);

  const setCachedOutline = (data: OutlineData) => {
    queryClient.setQueryData(["outline", documentId], data);
    void queryClient.invalidateQueries({ queryKey: ["outline-versions", documentId] });
    setSections(data.outline);
  };

  const handleError = (error: unknown) => {
    if ((error as { status?: number })?.status === 409) onLockConflict?.();
  };

  const generateMutation = useMutation({
    mutationFn: (regenerate: boolean) => {
      if (!documentId || !sourceItemId) throw new Error("缺少大纲所需的文档信息");
      return generateOutline(documentId, sourceItemId, lockVersion, regenerate);
    },
    onSuccess: (data) => {
      setAnswers({});
      setCachedOutline(data);
      setEditing(true);
    },
    onError: handleError,
  });

  const updateMutation = useMutation({
    mutationFn: () => {
      if (!documentId) throw new Error("缺少文档信息");
      return updateOutline(documentId, sections, answers, lockVersion);
    },
    onSuccess: (data) => {
      setCachedOutline(data);
      setEditing(true);
    },
    onError: handleError,
  });

  const confirmMutation = useMutation({
    mutationFn: async () => {
      if (!documentId) throw new Error("缺少文档信息");
      await updateOutline(documentId, sections, answers, lockVersion);
      return confirmOutline(documentId, lockVersion);
    },
    onSuccess: (data) => {
      setCachedOutline(data);
      setEditing(false);
    },
    onError: handleError,
  });

  const activateMutation = useMutation({
    mutationFn: (operationId: string) => {
      if (!documentId) throw new Error("缺少文档信息");
      return activateOutlineVersion(documentId, operationId, lockVersion);
    },
    onSuccess: (data) => {
      setAnswers({});
      setCachedOutline(data);
      setEditing(data.status === "draft");
    },
    onError: handleError,
  });

  const valid = useMemo(
    () => sections.length > 0 && sections.every((section) => section.heading.trim().length > 0),
    [sections],
  );
  const pending =
    generateMutation.isPending ||
    updateMutation.isPending ||
    confirmMutation.isPending ||
    activateMutation.isPending;
  const error =
    generateMutation.error ||
    updateMutation.error ||
    confirmMutation.error ||
    activateMutation.error;

  if (!documentId || !sourceItemId) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={outlineDialogLayout.content}>
        <DialogHeader className="shrink-0">
          <DialogTitle className="flex items-center gap-2 text-sm">
            <ListTree className="h-4 w-4" /> 回答大纲
            {outline ? (
              <span className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                O{outline.versionNumber}
              </span>
            ) : null}
          </DialogTitle>
        </DialogHeader>

        {versions.length > 0 ? (
          <div className="flex shrink-0 items-center gap-2 overflow-x-auto border-y py-2">
            <span className="flex shrink-0 items-center gap-1 text-[10px] text-muted-foreground">
              <History className="h-3 w-3" /> 历史
            </span>
            {versions.map((version) => {
              const active = version.operationId === outline?.operationId;
              return (
                <Button
                  key={version.operationId}
                  type="button"
                  variant={active ? "secondary" : "ghost"}
                  size="sm"
                  className="h-7 shrink-0 px-2 text-[10px]"
                  disabled={pending || active || !version.operationId}
                  onClick={() =>
                    version.operationId && activateMutation.mutate(version.operationId)
                  }
                  title={active ? "当前大纲版本" : `切换到大纲 O${version.versionNumber}`}
                >
                  O{version.versionNumber}
                  <span
                    className={
                      version.status === "confirmed" ? "text-emerald-600" : "text-amber-600"
                    }
                  >
                    {version.status === "confirmed" ? "已确认" : "草稿"}
                  </span>
                </Button>
              );
            })}
          </div>
        ) : null}

        <ScrollArea className={outlineDialogLayout.scrollArea}>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !outline ? (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-muted-foreground">
              <MessageSquare className="h-6 w-6 opacity-40" />
              <p className="text-xs">尚无大纲</p>
              <p className="text-[10px]">先由 AI 生成初稿，再按你的思路调整</p>
            </div>
          ) : (
            <div className="space-y-4 p-1">
              {outline.status === "confirmed" && !editing && (
                <div className="flex items-center justify-between rounded-lg border border-emerald-200 bg-emerald-50/60 px-3 py-2 dark:border-emerald-900 dark:bg-emerald-950/20">
                  <span className="flex items-center gap-2 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                    <CheckCircle className="h-3.5 w-3.5" /> 大纲已确认
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => setEditing(true)}
                  >
                    <Pencil className="h-3.5 w-3.5" /> 编辑大纲
                  </Button>
                </div>
              )}

              {outline.viewpointQuestions && outline.viewpointQuestions.length > 0 && editing && (
                <div className="space-y-2 rounded-lg border bg-muted/30 p-3">
                  <p className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
                    <HelpCircle className="h-3 w-3" /> 采访问题
                  </p>
                  {outline.viewpointQuestions.map((question, index) => (
                    <div key={question} className="flex items-start gap-2">
                      <span className="mt-1 shrink-0 text-[10px] text-muted-foreground">
                        Q{index + 1}.
                      </span>
                      <div className="flex-1 space-y-1">
                        <p className="text-[11px]">{question}</p>
                        <input
                          className="h-8 w-full rounded-md border bg-background px-2 text-[11px]"
                          placeholder="输入你的回答…"
                          value={answers[question] || ""}
                          onChange={(event) =>
                            setAnswers((value) => ({ ...value, [question]: event.target.value }))
                          }
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {editing ? (
                <OutlineEditor sections={sections} onChange={setSections} />
              ) : (
                <OutlinePreview sections={sections} />
              )}
            </div>
          )}
        </ScrollArea>

        {error ? <p className="text-xs text-destructive">{(error as Error).message}</p> : null}

        <div className="flex shrink-0 flex-wrap items-center gap-2 border-t pt-3">
          {!outline ? (
            <Button
              size="sm"
              className="h-8 text-xs"
              onClick={() => generateMutation.mutate(false)}
              disabled={pending}
            >
              {pending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" />
              )}
              生成大纲
            </Button>
          ) : (
            <>
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs"
                onClick={() => generateMutation.mutate(true)}
                disabled={pending}
              >
                <RefreshCw
                  className={`h-3.5 w-3.5 ${generateMutation.isPending ? "animate-spin" : ""}`}
                />
                重新生成
              </Button>
              {editing && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 text-xs"
                    onClick={() => updateMutation.mutate()}
                    disabled={pending || !valid}
                  >
                    <Save className="h-3.5 w-3.5" /> 保存大纲
                  </Button>
                  <Button
                    size="sm"
                    className="h-8 text-xs"
                    onClick={() => confirmMutation.mutate()}
                    disabled={pending || !valid}
                  >
                    <CheckCircle className="h-3.5 w-3.5" /> 保存并确认
                  </Button>
                </>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function OutlineEditor({
  sections,
  onChange,
}: {
  sections: EditableOutlineSection[];
  onChange: (sections: EditableOutlineSection[]) => void;
}) {
  return (
    <div className="space-y-3">
      {sections.map((section, sectionIndex) => (
        <div key={section.id ?? sectionIndex} className="rounded-xl border bg-card p-3 shadow-sm">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-muted text-[10px] font-bold text-muted-foreground">
              {sectionIndex + 1}
            </span>
            <input
              aria-label={`章节 ${sectionIndex + 1} 标题`}
              className="h-8 min-w-0 flex-1 rounded-md border bg-background px-2 text-xs font-semibold"
              value={section.heading}
              onChange={(event) =>
                onChange(updateSection(sections, sectionIndex, { heading: event.target.value }))
              }
              placeholder="章节标题"
            />
            <input
              aria-label={`章节 ${sectionIndex + 1} 预计字数`}
              type="number"
              min={50}
              max={5000}
              className="h-8 w-20 rounded-md border bg-background px-2 text-center text-[10px]"
              value={section.wordCountEstimate}
              onChange={(event) =>
                onChange(
                  updateSection(sections, sectionIndex, {
                    wordCountEstimate: Math.max(50, Number(event.target.value) || 50),
                  }),
                )
              }
            />
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-destructive"
              onClick={() => onChange(removeSection(sections, sectionIndex))}
              disabled={sections.length <= 1}
              title="删除章节"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>

          <div className="mt-3 space-y-2 pl-8">
            {section.keyPoints.map((keyPoint, keyPointIndex) => (
              <div key={keyPointIndex} className="flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground">•</span>
                <input
                  aria-label={`章节 ${sectionIndex + 1} 要点 ${keyPointIndex + 1}`}
                  className="h-8 min-w-0 flex-1 rounded-md border bg-background px-2 text-[11px]"
                  value={keyPoint}
                  onChange={(event) => {
                    const keyPoints = section.keyPoints.map((value, index) =>
                      index === keyPointIndex ? event.target.value : value,
                    );
                    onChange(updateSection(sections, sectionIndex, { keyPoints }));
                  }}
                  placeholder="核心要点"
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-muted-foreground hover:text-destructive"
                  onClick={() => onChange(removeKeyPoint(sections, sectionIndex, keyPointIndex))}
                  title="删除要点"
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-[11px]"
              onClick={() => onChange(addKeyPoint(sections, sectionIndex))}
            >
              <Plus className="h-3 w-3" /> 添加要点
            </Button>
          </div>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        className="h-8 w-full border-dashed text-xs"
        onClick={() => onChange(addSection(sections))}
      >
        <Plus className="h-3.5 w-3.5" /> 添加章节
      </Button>
    </div>
  );
}

function OutlinePreview({ sections }: { sections: EditableOutlineSection[] }) {
  return (
    <div className="space-y-2">
      {sections.map((section, index) => (
        <div key={section.id ?? index} className="rounded-lg border bg-card p-3">
          <div className="mb-1 flex items-center gap-2">
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-bold text-muted-foreground">
              {index + 1}
            </span>
            <span className="text-xs font-semibold">{section.heading}</span>
            <span className="ml-auto text-[9px] text-muted-foreground">
              约 {section.wordCountEstimate} 字
            </span>
          </div>
          {section.keyPoints.length > 0 && (
            <ul className="space-y-0.5 pl-5">
              {section.keyPoints.map((keyPoint, keyPointIndex) => (
                <li key={keyPointIndex} className="list-disc text-[10px] text-muted-foreground">
                  {keyPoint}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
