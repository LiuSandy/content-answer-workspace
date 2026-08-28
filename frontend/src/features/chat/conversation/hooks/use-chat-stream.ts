import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { apiGet, apiPost } from "@/lib/api";
import { streamPost } from "@/lib/sse";
import { useChatStore } from "@/store/chat-store";
import type { MultiAgentRunResult } from "../../tasks/types/multi-agent";
import type { ChatMessage } from "../model/chat-message-tree";
import {
  abortStreamForChat,
  reconcileTransientStreamError,
  type ActiveChatStream,
} from "../model/chat-stream-lifecycle";
import { createStreamingMessageController } from "../model/streaming-message-controller";

type StreamUiState = {
  isStreaming: boolean;
  activeTaskPlanId: string | null;
  multiAgentResult: MultiAgentRunResult | null;
};

const INITIAL_STREAM_UI: StreamUiState = {
  isStreaming: false,
  activeTaskPlanId: null,
  multiAgentResult: null,
};

const AGENT_STATUS_LABELS: Record<string, string> = {
  routing_intent: "分析意图...",
  generating: "生成回复中...",
};

const TOOL_STATUS_LABELS: Record<string, string> = {
  parse_url: "解析链接中...",
  collect: "采集帖子中...",
};

/** 管理 Chat 主线的 SSE 请求、生命周期和相关状态。 */
export function useChatStream(onStreamStart: () => void) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const {
    currentChatId,
    activeLeafMessageId,
    setCurrentChatId,
    setActiveLeafMessageId,
  } = useChatStore();
  const [ui, patchUi] = useReducer(
    (state: StreamUiState, patch: Partial<StreamUiState>) => ({ ...state, ...patch }),
    INITIAL_STREAM_UI,
  );
  const streamingController = useMemo(() => createStreamingMessageController(), []);
  const abortRef = useRef<ActiveChatStream | null>(null);
  const isStreamingRef = useRef(false);

  useEffect(() => {
    const handleTaskPlanCreated = (event: Event) => {
      const planId = (event as CustomEvent<{ planId?: string }>).detail?.planId;
      if (planId) patchUi({ activeTaskPlanId: planId });
    };
    window.addEventListener("taskplan:created", handleTaskPlanCreated);
    return () => window.removeEventListener("taskplan:created", handleTaskPlanCreated);
  }, []);

  useEffect(() => () => {
    const activeStream = abortRef.current;
    abortRef.current = abortStreamForChat(abortRef.current, currentChatId);
    if (activeStream?.chatId === currentChatId) streamingController.reset();
  }, [currentChatId, streamingController]);

  useEffect(() => {
    // 从欢迎页创建会话时，当前运行中的流属于新 chat，不能在路由更新时误清空。
    if (abortRef.current?.chatId === currentChatId) return;
    streamingController.reset();
    isStreamingRef.current = false;
    patchUi(INITIAL_STREAM_UI);
  }, [currentChatId, streamingController]);

  const refreshAfterStream = useCallback(async (
    chatId: string,
    controller: AbortController,
    refreshFallback = false,
  ) => {
    const ownsCurrentStream = () => (
      abortRef.current?.controller === controller && !controller.signal.aborted
    );
    if (!ownsCurrentStream()) return;

    streamingController.flush();
    queryClient.invalidateQueries({ queryKey: ["chats"] });
    const transientError = streamingController.getSnapshot().streamingError;

    try {
      const updatedMessages = await queryClient.fetchQuery<ChatMessage[]>({
        queryKey: ["messages", chatId],
        queryFn: () => apiGet(`/api/chats/${chatId}/messages`),
      });
      if (!ownsCurrentStream()) return;

      streamingController.settle(
        reconcileTransientStreamError(transientError, updatedMessages),
      );
      if (updatedMessages.length > 0) {
        setActiveLeafMessageId(updatedMessages[updatedMessages.length - 1].messageId);
      }
    } catch (refreshError) {
      if (!ownsCurrentStream()) return;

      console.error("刷新消息历史失败:", refreshError);
      queryClient.setQueryData<ChatMessage[]>(["messages", chatId], (previous = []) =>
        previous.filter((message) => message.messageId !== "temp-user-msg"),
      );
      streamingController.settle(
        transientError ?? (refreshFallback ? "消息已发送，但刷新历史失败，请手动刷新" : null),
      );
    } finally {
      if (abortRef.current?.controller === controller) {
        abortRef.current = null;
        isStreamingRef.current = false;
        patchUi({ isStreaming: false });
      }
    }
  }, [queryClient, setActiveLeafMessageId, streamingController]);

  const startStream = useCallback((status: string, clearWorkspace = true) => {
    isStreamingRef.current = true;
    patchUi(clearWorkspace ? {
      isStreaming: true,
      activeTaskPlanId: null,
      multiAgentResult: null,
    } : { isStreaming: true });
    streamingController.start(status);
    onStreamStart();
  }, [onStreamStart, streamingController]);

  const handleStreamEvent = useCallback((event: string, data: any) => {
    if (event === "agent.status") {
      streamingController.setStatus(AGENT_STATUS_LABELS[data.status] || data.status);
    } else if (event === "tool.started") {
      streamingController.setStatus(
        TOOL_STATUS_LABELS[data.tool_type] || `执行工具: ${data.tool_type}`,
      );
    } else if (event === "task_plan.created") {
      streamingController.setStatus("复合任务执行中...");
      if (data?.planId) patchUi({ activeTaskPlanId: data.planId });
    } else if (event === "multi_agent.status") {
      streamingController.setStatus("多 Agent 协作中...");
      if (data?.status) {
        patchUi({
          multiAgentResult: {
            runId: data.runId || "chat-run",
            status: data.status,
            agents: data.agents || [],
            finalContent: data.finalContent,
          },
        });
      }
    } else if (event === "message.delta") {
      streamingController.setStatus(null);
      streamingController.appendChunk(data.delta);
    } else if (event === "source.list.completed") {
      streamingController.setStatus(null);
      streamingController.setSourceList(data);
    } else if (event === "agent.error") {
      streamingController.setError(data.message || "生成超时已自动停止，请重试");
    } else if (event === "run.failed") {
      streamingController.setError(data.message || "请求处理失败");
    }
  }, [streamingController]);

  const sendMessage = useCallback(async (content: string, parentId?: string | null) => {
    const trimmedContent = content.trim();
    if (!trimmedContent || isStreamingRef.current) return false;

    startStream("发送中...");
    let activeChatId = currentChatId;
    if (!activeChatId) {
      try {
        const newChat = await apiPost<{ chatId: string; title: string }>("/api/chats", { title: "新对话" });
        activeChatId = newChat.chatId;
        setCurrentChatId(activeChatId);
        navigate(`/chat/${activeChatId}`);
        queryClient.invalidateQueries({ queryKey: ["chats"] });
      } catch (error) {
        console.error("创建会话失败:", error);
        streamingController.settle("初始化会话失败，请重试");
        isStreamingRef.current = false;
        patchUi({ isStreaming: false });
        return false;
      }
    }

    const parentMessageId = parentId !== undefined ? parentId : activeLeafMessageId;
    queryClient.setQueryData<ChatMessage[]>(["messages", activeChatId], (previous = []) => [
      ...previous,
      {
        messageId: "temp-user-msg",
        role: "user",
        messageType: "text",
        content: trimmedContent,
        parentMessageId,
        payload: null,
        createdAt: new Date().toISOString(),
      },
    ]);
    setActiveLeafMessageId("temp-user-msg");

    const controller = new AbortController();
    abortRef.current = { chatId: activeChatId, controller };
    try {
      await streamPost(`/api/chats/${activeChatId}/messages/stream`, {
        content: trimmedContent,
        parentMessageId,
      }, {
        onEvent: (event, data) => {
          if (abortRef.current?.controller === controller) handleStreamEvent(event, data);
        },
        onError: (error) => {
          if (abortRef.current?.controller === controller) {
            streamingController.setError(error.message);
          }
        },
      }, controller.signal);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        console.error("流式请求失败:", error);
      }
    } finally {
      await refreshAfterStream(activeChatId, controller, true);
    }
    return true;
  }, [
    activeLeafMessageId,
    currentChatId,
    handleStreamEvent,
    navigate,
    queryClient,
    refreshAfterStream,
    setActiveLeafMessageId,
    setCurrentChatId,
    startStream,
    streamingController,
  ]);

  const selectChoice = useCallback(async (optionId: string, messageId: string) => {
    if (isStreamingRef.current || !currentChatId) return;

    startStream("已选择，正在继续...", false);
    const controller = new AbortController();
    abortRef.current = { chatId: currentChatId, controller };
    try {
      await streamPost(`/api/chats/${currentChatId}/choices`, {
        messageId,
        selection: optionId,
      }, {
        onEvent: (event, data) => {
          if (abortRef.current?.controller !== controller) return;
          if (event === "run.failed") {
            streamingController.setError(data.message || "续跑失败，请重试");
            return;
          }
          handleStreamEvent(event, data);
        },
        onError: (error) => {
          if (abortRef.current?.controller === controller) {
            streamingController.setError(error.message);
          }
        },
      }, controller.signal);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        console.error("提交选择失败:", error);
      }
    } finally {
      await refreshAfterStream(currentChatId, controller);
    }
  }, [
    currentChatId,
    handleStreamEvent,
    refreshAfterStream,
    startStream,
    streamingController,
  ]);

  return {
    ...ui,
    streamingController,
    sendMessage,
    selectChoice,
  };
}
