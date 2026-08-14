export type SSECallbacks = {
  onEvent?: (event: string, data: any) => void;
  onError?: (error: Error) => void;
};

/**
 * 通过 POST 请求流式读取 SSE 数据。
 *
 * 支持传入 AbortSignal：调用方（如聊天面板）在切换会话或卸载时必须
 * 中断流，否则读取循环会继续向已失效的组件状态写入数据。
 * 中断产生的 AbortError 静默返回，不触发 onError。
 */
export async function streamPost(
  url: string,
  body: unknown,
  callbacks: SSECallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok || !response.body) {
    let errMsg = `HTTP ${response.status}`;
    try {
      const errPayload = await response.json();
      if (errPayload?.error?.message) {
        errMsg = errPayload.error.message;
      }
    } catch {
      // 忽略 JSON 解析失败
    }
    const error = new Error(errMsg);
    callbacks.onError?.(error);
    throw error;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function handleEventBlock(eventBlock: string) {
    const lines = eventBlock.split("\n");
    let eventName = "";
    const dataLines: string[] = [];

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("event:")) {
        eventName = trimmed.slice(6).trim();
      } else if (trimmed.startsWith("data:")) {
        dataLines.push(trimmed.slice(5).trim());
      }
    }

    if (!eventName && dataLines.length === 0) return;

    // SSE 规范要求多行 data 用换行拼接，空串拼接会破坏含换行的负载
    const rawData = dataLines.join("\n");
    let parsedData = rawData;
    try {
      parsedData = JSON.parse(rawData);
    } catch {
      // 保持原始字符串
    }

    callbacks.onEvent?.(eventName || "message", parsedData);
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE 事件以双换行符 \n\n 分隔
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";

      for (const eventBlock of events) {
        if (eventBlock.trim()) {
          handleEventBlock(eventBlock);
        }
      }
    }

    if (buffer.trim()) {
      handleEventBlock(buffer);
    }
  } catch (err) {
    // 主动中断不是错误：静默返回，避免误报给用户
    if (err instanceof DOMException && err.name === "AbortError") {
      return;
    }
    const error = err instanceof Error ? err : new Error(String(err));
    callbacks.onError?.(error);
    throw error;
  }
}
