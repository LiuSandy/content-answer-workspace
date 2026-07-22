import React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface RetrievalTraceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  traceData?: any;
}

export const RetrievalTraceDialog: React.FC<RetrievalTraceDialogProps> = ({
  open,
  onOpenChange,
  traceData,
}) => {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[650px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            🔍 检索调试日志 (Retrieval Trace)
            <Badge variant="outline">Debug Mode</Badge>
          </DialogTitle>
        </DialogHeader>

        <div className="my-2 p-3 bg-muted font-mono text-xs overflow-auto max-h-[350px] rounded border">
          <pre>{JSON.stringify(traceData || { message: "No trace data available" }, null, 2)}</pre>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
