import React, { useRef } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ArrowUp } from "lucide-react";
import { cn } from "@/lib/utils";

interface PromptInputProps {
  value: string;
  onChange: (val: string) => void;
  onSubmit: () => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  allowEmpty?: boolean;
  submitLabel?: string;
  submitIcon?: React.ReactNode;
}

export function PromptInput({
  value,
  onChange,
  onSubmit,
  placeholder = "请输入...",
  disabled = false,
  className,
  allowEmpty = false,
  submitLabel,
  submitIcon,
}: PromptInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && (allowEmpty || value.trim())) {
        onSubmit();
      }
    }
  };

  return (
    <div
      className={cn(
        "relative flex flex-col rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-1.5 focus-within:ring-2 focus-within:ring-indigo-500/20 focus-within:border-indigo-500 transition-all shadow-sm",
        className
      )}
    >
      <Textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        rows={3}
        className={cn(
          "w-full bg-transparent resize-none border-0 pl-3 py-2 text-sm placeholder:text-zinc-400 dark:placeholder:text-zinc-500 outline-none focus:outline-none focus:ring-0 focus-visible:ring-0 focus-visible:ring-offset-0 h-[84px] min-h-[84px] max-h-[84px] overflow-y-auto leading-relaxed text-zinc-800 dark:text-zinc-200 shadow-none focus-visible:ring-offset-0",
          submitLabel ? "pr-28" : "pr-12"
        )}
      />

      {submitLabel ? (
        <Button
          size="sm"
          disabled={disabled || (!allowEmpty && !value.trim())}
          onClick={onSubmit}
          className={cn(
            "absolute right-2 bottom-2 h-8 px-3 rounded-lg bg-indigo-500 hover:bg-indigo-600 text-white transition-colors shrink-0 gap-1.5 text-xs font-medium",
            (disabled || (!allowEmpty && !value.trim())) && "bg-indigo-100 text-zinc-400 dark:bg-indigo-950/40 dark:disabled:text-zinc-700"
          )}
        >
          {submitIcon}
          <span>{submitLabel}</span>
        </Button>
      ) : (
        <Button
          size="icon"
          disabled={disabled || (!allowEmpty && !value.trim())}
          onClick={onSubmit}
          className="absolute right-2 bottom-2 h-8 w-8 rounded-full bg-indigo-500 hover:bg-indigo-600 text-white disabled:bg-indigo-100 disabled:text-zinc-400 dark:bg-indigo-600 dark:hover:bg-indigo-700 dark:disabled:bg-indigo-950/40 dark:disabled:text-zinc-700 transition-colors shrink-0"
        >
          <ArrowUp className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}
