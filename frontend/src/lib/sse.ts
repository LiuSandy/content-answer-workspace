export type SseEvent<T> =
  | { type: "chunk"; text: string; itemId?: string }
  | { type: "item_start"; itemId: string }
  | { type: "item_done"; itemId: string; item: unknown }
  | { type: "tool_start"; text: string }
  | { type: "tool_end"; text: string }
  | { type: "done"; data: T }
  | { type: "error"; message: string };

export type SseCallbacks<T> = {
  onChunk?: (text: string, itemId?: string) => void;
  onItemStart?: (itemId: string) => void;
  onItemDone?: (itemId: string, item: unknown) => void;
  onToolStart?: (text: string) => void;
  onToolEnd?: (text: string) => void;
  onDone?: (data: T) => void;
  onError?: (message: string) => void;
};

export async function streamPost<T>(
  url: string,
  body: unknown,
  callbacks: SseCallbacks<T>,
): Promise<void> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok || !response.body) {
    callbacks.onError?.(`HTTP ${response.status}`);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 规范：以 \n\n 分隔事件
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const eventBlock of events) {
      if (!eventBlock.trim()) continue;
      // 提取所有 data: 行并拼接
      const dataLines = eventBlock
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim());
      if (dataLines.length === 0) continue;
      const raw = dataLines.join("");
      if (!raw) continue;
      try {
        const event = JSON.parse(raw) as SseEvent<T>;
        if (event.type === "chunk") callbacks.onChunk?.(event.text, event.itemId);
        else if (event.type === "item_start") callbacks.onItemStart?.(event.itemId);
        else if (event.type === "item_done") callbacks.onItemDone?.(event.itemId, event.item);
        else if (event.type === "tool_start") callbacks.onToolStart?.(event.text);
        else if (event.type === "tool_end") callbacks.onToolEnd?.(event.text);
        else if (event.type === "done") callbacks.onDone?.(event.data);
        else if (event.type === "error") callbacks.onError?.(event.message);
      } catch {
        // 忽略非 JSON 行
      }
    }
  }
}
