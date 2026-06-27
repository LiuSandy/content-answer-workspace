import { useState } from "react";
import { SendHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import { ChatToolsPopover } from "./chat-tools-popover";

type Props = {
  disabled: boolean;
  onSend: (message: string) => void;
};

export function ChatMessageInput({ disabled, onSend }: Props) {
  const [value, setValue] = useState("");

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || disabled) {
      return;
    }
    onSend(trimmed);
    setValue("");
  }

  return (
    // 整个外壳呈现为「一个」输入框：上方纯文本输入，下方工具栏行（左工具、右发送）
    <div className="m-3 flex flex-col gap-2 rounded-lg border bg-card p-2 focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 ring-offset-background">
      <Textarea
        className="min-h-[44px] resize-none border-0 bg-transparent p-1 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行..."
        value={value}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            handleSend();
          }
        }}
      />
      <div className="flex items-center justify-between">
        <ChatToolsPopover />
        <Button size="sm" disabled={!value.trim() || disabled} onClick={handleSend}>
          发送
          <SendHorizontal />
        </Button>
      </div>
    </div>
  );
}
