import React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface ReconvertDiffDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  diffContent?: string;
  onConfirmReplace: () => void;
}

export const ReconvertDiffDialog: React.FC<ReconvertDiffDialogProps> = ({
  open,
  onOpenChange,
  diffContent = "",
  onConfirmReplace,
}) => {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>重新转换版本差异对比 (Diff)</DialogTitle>
          <DialogDescription>
            该资料曾存在人工修改。重新解析源文件产生了新的候选版本，请确认是否覆盖当前版本并重新索引。
          </DialogDescription>
        </DialogHeader>

        <div className="my-2 p-3 bg-muted font-mono text-xs overflow-auto max-h-[300px] rounded border space-y-1">
          {diffContent ? (
            diffContent.split("\n").map((line, idx) => {
              const isAdd = line.startsWith("+");
              const isDel = line.startsWith("-");
              return (
                <div
                  key={idx}
                  className={
                    isAdd
                      ? "text-emerald-500 bg-emerald-500/10 px-1"
                      : isDel
                      ? "text-rose-500 bg-rose-500/10 px-1"
                      : "text-muted-foreground"
                  }
                >
                  {line}
                </div>
              );
            })
          ) : (
            <p className="text-muted-foreground">未检测到明显差异。</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => {
              onConfirmReplace();
              onOpenChange(false);
            }}
          >
            确认使用候选版本并重新索引
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
