import { useEffect, useRef, useState } from "react";
import { BubbleMenu } from "@tiptap/react/menus";
import type { useEditor } from "@tiptap/react";
import { Wand2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";

export type InlineRefineParams = {
  from: number;
  to: number;
  text: string;
  instruction: string;
};

/**
 * 选区局部优化菜单：划选文字后浮动展示「局部优化」按钮，点击后弹出对话框
 * 输入优化指令，由父组件（editor-panel.tsx）负责调用 LLM 精修并替换选区。
 *
 * 独立成组件的原因：BubbleMenu + Dialog + 选区快照这套交互与编辑器主体的
 * 生成 / 重写逻辑完全无关，抽出后避免 editor-panel.tsx 进一步膨胀（已接近
 * 800 行上限），也便于未来单独调整这块 UI。
 */
export function InlineRefineMenu({
  editor,
  isGenerating,
  onRefine,
}: {
  editor: ReturnType<typeof useEditor>;
  isGenerating: boolean;
  onRefine: (params: InlineRefineParams) => void;
}) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [instruction, setInstruction] = useState("");
  // 选区在打开对话框瞬间就被快照记录，避免对话框弹出导致编辑器失焦、
  // 选区被清空后再读取 editor.state.selection 读到错误的结果。
  const selectionSnapshotRef = useRef<{ from: number; to: number; text: string } | null>(null);

  // shouldShow 回调在插件创建时闭包捕获 isGenerating，用 ref 存最新值避免拿到过期状态。
  const isGeneratingRef = useRef(isGenerating);
  useEffect(() => {
    isGeneratingRef.current = isGenerating;
  }, [isGenerating]);

  if (!editor) return null;

  const handleOpenDialog = () => {
    const { from, to } = editor.state.selection;
    if (from === to) return;
    // 不能用 textBetween 取纯文本：后端 current_content 存储的是原始 Markdown 字符串，
    // 选区跨越粗体/标题等标记时纯文本会丢失标记字符，导致与原文无法按子串匹配。
    // 用 doc.cut 裁出选区对应的文档片段（仍是合法的 "doc" 节点树），再交给 tiptap-markdown
    // 的序列化器按与全文档一致的规则渲染，得到的字符串才是原 Markdown 中真正的连续子串。
    const cutDoc = editor.state.doc.cut(from, to);
    const text = (editor as any).markdown.serialize(cutDoc.toJSON());
    selectionSnapshotRef.current = { from, to, text };
    // 对话框打开后编辑器会失焦，浏览器原生选区渲染随之消失；用持久 Decoration
    // 高亮同一范围，让用户在填写指令期间仍能看到自己选中的内容。
    editor.commands.setSelectionHighlight(from, to);
    setInstruction("");
    setDialogOpen(true);
  };

  const handleSubmit = () => {
    const snapshot = selectionSnapshotRef.current;
    if (!snapshot || !instruction.trim()) return;
    editor.commands.clearSelectionHighlight();
    onRefine({ ...snapshot, instruction: instruction.trim() });
    setDialogOpen(false);
  };

  const handleDialogOpenChange = (open: boolean) => {
    if (!open) {
      editor.commands.clearSelectionHighlight();
    }
    setDialogOpen(open);
  };

  return (
    <>
      <BubbleMenu
        editor={editor}
        shouldShow={({ from, to }) => from !== to && !isGeneratingRef.current}
        className="flex items-center gap-1 rounded-md border border-border bg-popover p-1 shadow-md"
      >
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 px-2 text-xs text-popover-foreground"
          onClick={handleOpenDialog}
        >
          <Wand2 className="h-3.5 w-3.5" />
          局部优化
        </Button>
      </BubbleMenu>

      <Dialog open={dialogOpen} onOpenChange={handleDialogOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>局部优化</DialogTitle>
            <DialogDescription>
              描述如何优化选中的内容，AI 会结合前后文重新生成该片段，保证衔接通顺。
            </DialogDescription>
          </DialogHeader>
          <Textarea
            autoFocus
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="例如：让这段话更简洁有力 / 补充一个具体的例子 / 换一种更口语化的说法"
            className="min-h-[100px]"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => handleDialogOpenChange(false)}>
              取消
            </Button>
            <Button onClick={handleSubmit} disabled={!instruction.trim()}>
              开始优化
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
