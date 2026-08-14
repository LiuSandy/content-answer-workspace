import React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export interface ReconvertDiffDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  oldMarkdown?: string;
  newMarkdown?: string;
  onApplyNew: () => void;
}

export const ReconvertDiffDialog: React.FC<ReconvertDiffDialogProps> = ({
  open,
  onOpenChange,
  oldMarkdown = "",
  newMarkdown = "",
  onApplyNew,
}) => {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>重新解析对比 (Diff Viewer)</DialogTitle>
        </DialogHeader>
        <div className="flex-1 grid grid-cols-2 gap-4 min-h-0 py-2">
          <div className="flex flex-col border rounded-md p-3 bg-muted/20 overflow-hidden">
            <div className="text-xs font-semibold mb-2 text-muted-foreground">当前/旧解析版本</div>
            <pre className="flex-1 overflow-auto font-mono text-xs whitespace-pre-wrap text-foreground">
              {oldMarkdown}
            </pre>
          </div>
          <div className="flex flex-col border rounded-md p-3 bg-accent/20 overflow-hidden">
            <div className="text-xs font-semibold mb-2 text-primary">新重新解析候选版本</div>
            <pre className="flex-1 overflow-auto font-mono text-xs whitespace-pre-wrap text-foreground">
              {newMarkdown}
            </pre>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            放弃
          </Button>
          <Button onClick={onApplyNew}>
            应用新解析版本
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
