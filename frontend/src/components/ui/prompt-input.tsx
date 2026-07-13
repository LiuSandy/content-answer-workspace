import React, { useRef, useState, useEffect } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ArrowUp, Sparkles, ChevronDown } from "lucide-react";
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
  selectedStyles?: string[];
  onSelectedStylesChange?: (styles: string[]) => void;
  wordCount?: number;
  onWordCountChange?: (v: number) => void;
}

const WRITING_STYLES = [
  { id: "professional", label: "专业严谨" },
  { id: "humorous", label: "幽默风趣" },
  { id: "detailed", label: "干货满满" },
  { id: "emotional", label: "感性生动" },
  { id: "concise", label: "简明扼要" },
];

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
  selectedStyles,
  onSelectedStylesChange,
  wordCount,
  onWordCountChange,
}: PromptInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const showStyles = selectedStyles !== undefined && onSelectedStylesChange !== undefined;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && (allowEmpty || value.trim())) {
        onSubmit();
      }
    }
  };

  // 点击外部关闭风格下拉框
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // 风格按钮展示文本
  const getStyleButtonLabel = () => {
    if (!selectedStyles || selectedStyles.length === 0) {
      return "风格: 默认";
    }
    const labels = selectedStyles
      .map((id) => WRITING_STYLES.find((s) => s.id === id)?.label)
      .filter(Boolean);
    if (labels.length <= 1) {
      return `风格: ${labels[0]}`;
    }
    return `风格: ${labels[0]}...`;
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
          submitLabel ? "pr-28" : "pr-12",
          showStyles ? "pb-10" : ""
        )}
      />

      {/* ── 底部左侧：写作风格选择器与字数要求 ── */}
      {showStyles && selectedStyles && onSelectedStylesChange && (
        <div className="absolute left-2.5 bottom-2 flex items-center gap-2">
          <div ref={dropdownRef} className="relative">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDropdownOpen(!dropdownOpen)}
              disabled={disabled}
              className={cn(
                "h-8 px-2.5 rounded-lg text-xs gap-1.5 font-medium transition-colors shrink-0",
                selectedStyles.length > 0
                  ? "bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-950/60"
                  : "text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              )}
            >
              <Sparkles className="h-3.5 w-3.5" />
              <span>{getStyleButtonLabel()}</span>
              <ChevronDown className={cn("h-3 w-3 opacity-60 transition-transform", dropdownOpen && "rotate-180")} />
            </Button>

            {/* 浮动下拉面板 (向上弹出) */}
            {dropdownOpen && (
              <div className="absolute bottom-[38px] left-0 z-50 w-44 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-2 shadow-lg flex flex-col gap-0.5">
                <span className="text-[10px] font-bold text-zinc-400 dark:text-zinc-500 px-2 py-1 uppercase tracking-wider select-none">
                  选择写作风格
                </span>
                {WRITING_STYLES.map((style) => {
                  const checked = selectedStyles.includes(style.id);
                  return (
                    <label
                      key={style.id}
                      className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-zinc-50 dark:hover:bg-zinc-800 text-xs text-zinc-700 dark:text-zinc-300 font-medium cursor-pointer select-none"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          const next = checked
                            ? selectedStyles.filter((id) => id !== style.id)
                            : [...selectedStyles, style.id];
                          onSelectedStylesChange(next);
                        }}
                        className="rounded border-zinc-300 dark:border-zinc-700 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5 cursor-pointer"
                      />
                      <span>{style.label}</span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>

          {/* 字数限制（默认 1000，最多 5000） */}
          {wordCount !== undefined && onWordCountChange && (
            <div className="flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400 select-none">
              <span className="h-3.5 w-px bg-zinc-200 dark:bg-zinc-800 mx-0.5" />
              <label htmlFor="word-count-input" className="font-medium shrink-0">字数:</label>
              <input
                id="word-count-input"
                type="number"
                value={wordCount || ""}
                onChange={(e) => {
                  const val = e.target.value === "" ? 0 : parseInt(e.target.value, 10);
                  onWordCountChange(val);
                }}
                onBlur={(e) => {
                  let val = parseInt(e.target.value, 10);
                  if (isNaN(val) || val < 100) {
                    val = 100;
                  } else if (val > 5000) {
                    val = 5000;
                  }
                  onWordCountChange(val);
                }}
                disabled={disabled}
                className="w-16 h-7 px-1 border border-zinc-200 dark:border-zinc-800 rounded-lg text-xs bg-transparent text-center font-mono outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/20 [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none [appearance:textfield]"
              />
              <span className="font-medium shrink-0">字</span>
            </div>
          )}
        </div>
      )}

      {/* ── 底部右侧：发送按钮 ── */}
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
