import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2, ListTree, Plus, Pencil, RefreshCw, CheckCircle, HelpCircle, MessageSquare } from "lucide-react";

interface OutlineSection {
  id?: string;
  order?: number;
  heading: string;
  keyPoints: string[];
  wordCountEstimate: number;
}

interface OutlineData {
  operationId?: string;
  status: "draft" | "confirmed";
  viewpointQuestions: string[] | null;
  outline: OutlineSection[];
}

interface OutlineDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentId: string | null;
  sourceItemId: string | null;
  lockVersion: number;
  onLockConflict?: () => void;
}

async function getOutline(documentId: string): Promise<OutlineData | null> {
  const res = await fetch(`/api/documents/${documentId}/outline/current`);
  const json = await res.json();
  return json.data;
}

async function generateOutline(documentId: string, sourceItemId: string, lockVersion: number) {
  const res = await fetch(`/api/documents/${documentId}/outline/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sourceItemId, expectedLockVersion: lockVersion }),
  });
  if (!res.ok) throw new Error((await res.json()).error || "generate failed");
  return (await res.json()).data as OutlineData;
}

async function confirmOutline(documentId: string, lockVersion: number) {
  const res = await fetch(`/api/documents/${documentId}/outline/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expectedLockVersion: lockVersion }),
  });
  if (!res.ok) throw new Error((await res.json()).error || "confirm failed");
  return (await res.json()).data as OutlineData;
}

export function OutlineDialog({
  open,
  onOpenChange,
  documentId,
  sourceItemId,
  lockVersion,
  onLockConflict,
}: OutlineDialogProps) {
  const qc = useQueryClient();
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const { data: outline, isLoading } = useQuery<OutlineData | null>({
    queryKey: ["outline", documentId],
    queryFn: () => (documentId ? getOutline(documentId) : null),
    enabled: open && !!documentId,
  });

  const generateMut = useMutation({
    mutationFn: () => {
      if (!documentId || !sourceItemId) return Promise.reject("missing ids");
      return generateOutline(documentId, sourceItemId, lockVersion);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["outline", documentId] }),
  });

  const confirmMut = useMutation({
    mutationFn: () => {
      if (!documentId) return Promise.reject("missing id");
      return confirmOutline(documentId, lockVersion);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["outline", documentId] }),
  });

  if (!documentId || !sourceItemId) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <ListTree className="h-4 w-4" /> 回答大纲
          </DialogTitle>
        </DialogHeader>

        <ScrollArea className="flex-1 max-h-[60vh]">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : outline && outline.status === "confirmed" ? (
            <div className="space-y-3 p-1">
              <div className="flex items-center gap-2 text-xs text-green-600 font-medium mb-2">
                <CheckCircle className="h-3.5 w-3.5" /> 大纲已确认
              </div>
              <OutlinePreview sections={outline.outline} />
            </div>
          ) : outline && outline.outline.length > 0 ? (
            <div className="space-y-3 p-1">
              {outline.viewpointQuestions && outline.viewpointQuestions.length > 0 && (
                <div className="border border-border rounded p-3 bg-muted/30 space-y-2 mb-3">
                  <p className="text-[11px] font-medium flex items-center gap-1 text-muted-foreground">
                    <HelpCircle className="h-3 w-3" /> 采访问题
                  </p>
                  {outline.viewpointQuestions.map((q, i) => (
                    <div key={i} className="flex gap-2 items-start">
                      <span className="text-[10px] text-muted-foreground mt-1 shrink-0">Q{i + 1}.</span>
                      <div className="flex-1 space-y-1">
                        <p className="text-[11px]">{q}</p>
                        <input
                          className="w-full h-7 text-[11px] px-2 rounded border border-border bg-background"
                          placeholder="输入你的回答…"
                          value={answers[q] || ""}
                          onChange={(e) => setAnswers((a) => ({ ...a, [q]: e.target.value }))}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <OutlinePreview sections={outline.outline} />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
              <MessageSquare className="h-6 w-6 opacity-40" />
              <p className="text-xs">尚无大纲</p>
              <p className="text-[10px]">点击下方按钮根据来源材料生成回答大纲</p>
            </div>
          )}
        </ScrollArea>

        <div className="flex items-center gap-2 pt-3 border-t border-border mt-2">
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7"
            onClick={() => generateMut.mutate()}
            disabled={generateMut.isPending}
          >
            {generateMut.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
            ) : (
              <Plus className="h-3.5 w-3.5 mr-1" />
            )}
            生成大纲
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7"
            onClick={() => {
              setAnswers({});
              generateMut.mutate();
            }}
            disabled={generateMut.isPending}
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            重新生成
          </Button>
          {outline && outline.outline.length > 0 && outline.status !== "confirmed" && (
            <Button
              variant="default"
              size="sm"
              className="text-xs h-7"
              onClick={() => confirmMut.mutate()}
              disabled={confirmMut.isPending}
            >
              <CheckCircle className="h-3.5 w-3.5 mr-1" />
              确认大纲
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function OutlinePreview({ sections }: { sections: OutlineSection[] }) {
  return (
    <div className="space-y-2">
      {sections.map((s, i) => (
        <div key={i} className="border border-border rounded p-2.5 bg-card">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
              {i + 1}
            </span>
            <span className="text-xs font-semibold">{s.heading}</span>
            <span className="text-[9px] text-muted-foreground ml-auto">
              ~{s.wordCountEstimate} 字
            </span>
          </div>
          {s.keyPoints.length > 0 && (
            <ul className="pl-5 space-y-0.5">
              {s.keyPoints.map((kp, j) => (
                <li key={j} className="text-[10px] text-muted-foreground list-disc">
                  {kp}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
