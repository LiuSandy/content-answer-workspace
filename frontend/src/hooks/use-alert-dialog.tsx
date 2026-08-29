import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { PropsWithChildren } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

type ConfirmOptions = {
  title?: string;
  description: string;
  confirmText?: string;
  cancelText?: string;
  variant?: "default" | "destructive";
};

type NotifyOptions = {
  title?: string;
  description: string;
  confirmText?: string;
};

type PendingRequest =
  | { kind: "confirm"; options: ConfirmOptions; resolve: (result: boolean) => void }
  | { kind: "notify"; options: NotifyOptions; resolve: () => void };

type AlertDialogContextValue = {
  /** 弹出二选一确认对话框，替代原生 confirm()；resolve(true) 表示用户点击了确认 */
  confirm: (options: ConfirmOptions | string) => Promise<boolean>;
  /** 弹出单按钮通知对话框，替代原生 alert() */
  notify: (options: NotifyOptions | string) => Promise<void>;
};

const AlertDialogContext = createContext<AlertDialogContextValue | null>(null);

/**
 * 全局确认/通知对话框 Provider：原生 alert()/confirm() 是同步阻塞调用，
 * 无法适配 React 声明式渲染，这里用一个单例 AlertDialog + Promise 队列
 * 把「异步等待用户点击」封装成 async/await 风格的 confirm()/notify()，
 * 挂载一次即可在任意组件通过 useAlertDialog() 调用，无需每处自行管理弹窗状态。
 */
export function AlertDialogProvider({ children }: PropsWithChildren) {
  const [pending, setPending] = useState<PendingRequest | null>(null);
  // 弹窗关闭动画期间 pending 需要保留内容，用 ref 记录「是否已产生结果」避免重复 resolve
  const settledRef = useRef(false);

  const confirm = useCallback((options: ConfirmOptions | string): Promise<boolean> => {
    const normalized = typeof options === "string" ? { description: options } : options;
    return new Promise<boolean>((resolve) => {
      settledRef.current = false;
      setPending({ kind: "confirm", options: normalized, resolve });
    });
  }, []);

  const notify = useCallback((options: NotifyOptions | string): Promise<void> => {
    const normalized = typeof options === "string" ? { description: options } : options;
    return new Promise<void>((resolve) => {
      settledRef.current = false;
      setPending({ kind: "notify", options: normalized, resolve });
    });
  }, []);

  const settle = useCallback(
    (result: boolean) => {
      if (settledRef.current || !pending) return;
      settledRef.current = true;
      if (pending.kind === "confirm") {
        pending.resolve(result);
      } else {
        pending.resolve();
      }
      // 必须清空 pending 才能让 AlertDialog 的 open 状态归位，否则弹窗会停留在打开状态
      setPending(null);
    },
    [pending],
  );

  const contextValue = useMemo(() => ({ confirm, notify }), [confirm, notify]);

  const isOpen = pending !== null;
  const isConfirm = pending?.kind === "confirm";
  const confirmOptions = pending?.kind === "confirm" ? pending.options : null;
  const notifyOptions = pending?.kind === "notify" ? pending.options : null;

  return (
    <AlertDialogContext.Provider value={contextValue}>
      {children}
      <AlertDialog
        open={isOpen}
        onOpenChange={(open) => {
          if (!open) settle(false);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {(isConfirm ? confirmOptions?.title : notifyOptions?.title) ??
                (isConfirm ? "请确认" : "提示")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {isConfirm ? confirmOptions?.description : notifyOptions?.description}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            {isConfirm && (
              <AlertDialogCancel onClick={() => settle(false)}>
                {confirmOptions?.cancelText ?? "取消"}
              </AlertDialogCancel>
            )}
            <AlertDialogAction
              onClick={() => settle(true)}
              className={
                isConfirm && confirmOptions?.variant === "destructive"
                  ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  : undefined
              }
            >
              {(isConfirm ? confirmOptions?.confirmText : notifyOptions?.confirmText) ?? "确定"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AlertDialogContext.Provider>
  );
}

export function useAlertDialog(): AlertDialogContextValue {
  const ctx = useContext(AlertDialogContext);
  if (!ctx) {
    throw new Error("useAlertDialog 必须在 AlertDialogProvider 内部使用");
  }
  return ctx;
}
