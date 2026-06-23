/**
 * 主题管理分区；列表 + 新增/编辑 Dialog + 删除确认，因为主题是唯一需要 CRUD 的配置项。
 */

import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { TopicItem } from "./settings-api";
import {
  useCreateTopic,
  useDeleteTopic,
  useTopics,
  useUpdateTopic,
} from "./use-settings";

const EMPTY_TOPIC: TopicItem = {
  id: "",
  name: "",
  keywords: [],
  expandedHints: [],
  answerStyle: "",
  systemPrompt: "",
};

function TopicDialog({
  open,
  onClose,
  initial,
  onSave,
  isPending,
}: {
  open: boolean;
  onClose: () => void;
  initial: TopicItem;
  onSave: (t: TopicItem) => void;
  isPending: boolean;
}) {
  const [form, setForm] = useState<TopicItem>(initial);

  function set<K extends keyof TopicItem>(key: K, val: TopicItem[K]) {
    setForm((prev) => ({ ...prev, [key]: val }));
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{initial.id ? "编辑主题" : "新增主题"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>ID（英文，唯一）</Label>
              <Input
                value={form.id}
                onChange={(e) => set("id", e.target.value)}
                placeholder="my-topic"
                disabled={!!initial.id}
                className="font-mono text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <Label>名称</Label>
              <Input
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="我的主题"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>关键词（逗号分隔）</Label>
            <Input
              value={form.keywords.join(", ")}
              onChange={(e) =>
                set("keywords", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))
              }
              placeholder="关键词1, 关键词2"
            />
          </div>
          <div className="space-y-1.5">
            <Label>回答风格</Label>
            <Textarea
              value={form.answerStyle}
              onChange={(e) => set("answerStyle", e.target.value)}
              rows={2}
              placeholder="简短、结构清晰…"
            />
          </div>
          <div className="space-y-1.5">
            <Label>System Prompt</Label>
            <Textarea
              value={form.systemPrompt}
              onChange={(e) => set("systemPrompt", e.target.value)}
              rows={4}
              placeholder="你是一个…"
              className="font-mono text-xs"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button onClick={() => onSave(form)} disabled={isPending || !form.id || !form.name}>
            {isPending ? "保存中…" : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TopicsSettings() {
  const { data: topics = [], isLoading } = useTopics();
  const createTopic = useCreateTopic();
  const updateTopic = useUpdateTopic();
  const deleteTopic = useDeleteTopic();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<TopicItem | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  function openCreate() {
    setEditing(null);
    setDialogOpen(true);
  }

  function openEdit(t: TopicItem) {
    setEditing(t);
    setDialogOpen(true);
  }

  async function handleSave(form: TopicItem) {
    if (editing) {
      await updateTopic.mutateAsync({ id: editing.id, topic: form });
    } else {
      await createTopic.mutateAsync(form);
    }
    setDialogOpen(false);
  }

  if (isLoading) return <div className="text-sm text-muted-foreground">加载中…</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">共 {topics.length} 个主题</p>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4 mr-1.5" />
          新增主题
        </Button>
      </div>

      <div className="rounded-lg border divide-y">
        {topics.map((t) => (
          <div key={t.id} className="flex items-start gap-3 px-4 py-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium">{t.name}</span>
                <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                  {t.id}
                </span>
              </div>
              <div className="flex flex-wrap gap-1 mt-1.5">
                {t.keywords.slice(0, 6).map((kw) => (
                  <Badge key={kw} variant="secondary" className="text-[10px] h-4 px-1.5">
                    {kw}
                  </Badge>
                ))}
                {t.keywords.length > 6 && (
                  <span className="text-[10px] text-muted-foreground">+{t.keywords.length - 6}</span>
                )}
              </div>
            </div>
            <div className="flex gap-1 shrink-0">
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(t)}>
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-destructive hover:text-destructive"
                onClick={() => setDeleteId(t.id)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        ))}
        {topics.length === 0 && (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">
            还没有主题，点击「新增主题」创建。
          </div>
        )}
      </div>

      {/* 新增 / 编辑 Dialog */}
      <TopicDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        initial={editing ?? EMPTY_TOPIC}
        onSave={handleSave}
        isPending={createTopic.isPending || updateTopic.isPending}
      />

      {/* 删除确认 Dialog */}
      <Dialog open={!!deleteId} onOpenChange={(v) => !v && setDeleteId(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            删除主题「{topics.find((t) => t.id === deleteId)?.name}」后无法恢复。
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteId(null)}>取消</Button>
            <Button
              variant="default"
              className="bg-destructive hover:bg-destructive/90"
              disabled={deleteTopic.isPending}
              onClick={async () => {
                if (deleteId) {
                  await deleteTopic.mutateAsync(deleteId);
                  setDeleteId(null);
                }
              }}
            >
              {deleteTopic.isPending ? "删除中…" : "删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
