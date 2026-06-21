import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

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
    <div className="flex items-end gap-2 border-t p-3">
      <Textarea
        className="min-h-[44px] flex-1 resize-none"
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
      <Button disabled={!value.trim() || disabled} onClick={handleSend}>
        发送
      </Button>
    </div>
  );
}
