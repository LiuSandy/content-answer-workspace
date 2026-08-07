import {useState, useRef, useEffect} from "react";
import {useQuery, useQueryClient} from "@tanstack/react-query";
import {
    Send,
    Globe,
    Loader2,
    Sparkles,
    AlertCircle,
    FileText,
    Copy,
    Check,
    Pencil,
    ChevronLeft,
    ChevronRight,
    Wrench,
    ArrowUp,
    Clock
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {useNavigate} from "react-router-dom";

import {apiGet, apiPost} from "@/lib/api";
import {streamPost} from "@/lib/sse";
import {useChatStore} from "@/store/chat-store";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import {Card, CardContent} from "@/components/ui/card";
import {Badge} from "@/components/ui/badge";
import {ScrollArea} from "@/components/ui/scroll-area";
import {Skeleton} from "@/components/ui/skeleton";
import {TaskPlanCard} from "./task-plan-card";
import {MemoryAppliedBadge} from "./memory-applied-badge";
import {AgentWorkspacePanel, type MultiAgentRunResult} from "./agent-workspace-panel";
import {cn} from "@/lib/utils";
import {PromptInput} from "@/components/ui/prompt-input";
import {Textarea} from "@/components/ui/textarea";
import {SourceList} from "@/features/knowledge/source-list";

type Message = {
    messageId: string;
    role: "user" | "assistant" | "tool";
    messageType: "text" | "source_card" | "source_list" | "tool_status" | "error" | "choice_request";
    content: string | null;
    parentMessageId?: string | null;
    payload: any;
    createdAt: string;
};

/**
 * 解析并关联虚拟 parentMessageId 以防范旧的线性消息（parentMessageId 为 null）被误判为 siblings 兄弟分支。
 */
function resolveParentIds(allMsgs: Message[]): Message[] {
    const sorted = [...allMsgs].sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
    const resolved = sorted.map(m => ({...m}));

    for (let i = 0; i < resolved.length; i++) {
        const msg = resolved[i];
        if (msg.parentMessageId === undefined || msg.parentMessageId === null) {
            if (i === 0) {
                msg.parentMessageId = null;
                continue;
            }

            const prevMsg = resolved[i - 1];

            if (msg.role === "assistant" || msg.role === "tool") {
                msg.parentMessageId = prevMsg.messageId;
            } else if (msg.role === "user") {
                const nextMsg = resolved[i + 1];
                if (nextMsg && (nextMsg.role === "assistant" || nextMsg.role === "tool")) {
                    const nextMsgDbParent = allMsgs.find(m => m.messageId === nextMsg.messageId)?.parentMessageId;
                    if (!nextMsgDbParent || nextMsgDbParent !== msg.messageId) {
                        msg.parentMessageId = prevMsg.messageId;
                    } else {
                        msg.parentMessageId = null;
                    }
                } else {
                    msg.parentMessageId = prevMsg.messageId;
                }
            }
        }
    }
    return resolved;
}

/** Custom Markdown renderer components with premium designs */
const getMarkdownComponents = (isUser: boolean) => ({
    h1: ({node, ...props}: any) => (
        <h1 className={cn("text-lg font-bold mt-4 mb-2 border-b pb-1", isUser ? "text-primary-foreground border-primary-foreground/20" : "text-foreground border-border/40")} {...props} />
    ),
    h2: ({node, ...props}: any) => (
        <h2 className={cn("text-base font-bold mt-3.5 mb-1.5", isUser ? "text-primary-foreground/90" : "text-foreground")} {...props} />
    ),
    h3: ({node, ...props}: any) => (
        <h3 className={cn("text-sm font-bold mt-3 mb-1", isUser ? "text-primary-foreground/85" : "text-foreground/90")} {...props} />
    ),
    p: ({node, ...props}: any) => <p className="text-sm leading-relaxed mb-2 last:mb-0" {...props} />,
    ul: ({node, ...props}: any) => <ul className="list-disc pl-5 mb-3 space-y-1 text-sm" {...props} />,
    ol: ({node, ...props}: any) => <ol className="list-decimal pl-5 mb-3 space-y-1 text-sm" {...props} />,
    li: ({node, ...props}: any) => <li className="text-sm leading-relaxed" {...props} />,
    blockquote: ({node, ...props}: any) => (
        <blockquote
            className={cn("border-l-4 pl-3 my-2 italic", isUser ? "border-primary-foreground/30 text-primary-foreground/75" : "border-muted-foreground/30 text-muted-foreground")} {...props} />
    ),
    code: ({node, inline, className, children, ...props}: any) => {
        return !inline ? (
            <pre
                className="bg-muted/80 text-foreground p-3.5 rounded-xl my-2 overflow-x-auto text-xs font-mono border border-border/30 max-w-full">
        <code className={className} {...props}>{children}</code>
      </pre>
        ) : (
            <code
                className={cn("px-1 py-0.5 rounded text-xs font-mono border", isUser ? "bg-primary-foreground/10 text-primary-foreground border-primary-foreground/20" : "bg-muted text-foreground border-border/30")} {...props}>{children}</code>
        );
    },
    table: ({node, ...props}: any) => (
        <div className="my-3 overflow-x-auto rounded-lg border border-border/30 max-w-full">
            <table className="min-w-full divide-y divide-border/30 text-xs" {...props} />
        </div>
    ),
    thead: ({node, ...props}: any) => <thead className="bg-muted/40 font-semibold" {...props} />,
    tbody: ({node, ...props}: any) => <tbody className="divide-y divide-border/20" {...props} />,
    tr: ({node, ...props}: any) => <tr className="hover:bg-muted/5" {...props} />,
    th: ({node, ...props}: any) => <th className="px-3 py-2 text-left font-semibold text-foreground/80" {...props} />,
    td: ({node, ...props}: any) => <td className="px-3 py-2 text-foreground/75" {...props} />,
    a: ({node, ...props}: any) => (
        <a className={cn("hover:underline break-all font-medium", isUser ? "text-primary-foreground" : "text-blue-500")}
           target="_blank" rel="noreferrer" {...props} />
    )
});

/**
 * 中间对话面板：多轮消息列表 + 底部输入框。
 *
 * 支持提问复制、提问重新编辑和版本分支切换。
 */
export function ChatPanel() {
    const queryClient = useQueryClient();
    const navigate = useNavigate();
    const {
        currentChatId,
        setCurrentChatId,
        setSelectedSourceItemId,
        selectedSourceItemId,
        activeLeafMessageId,
        setActiveLeafMessageId
    } = useChatStore();
    const [inputText, setInputText] = useState("");

    // 流式交互临时状态
    const [isStreaming, setIsStreaming] = useState(false);
    const [agentStatus, setAgentStatus] = useState<string | null>(null);
    const [streamingText, setStreamingText] = useState("");
    const [streamingSourceList, setStreamingSourceList] = useState<any | null>(null);
    const [streamingError, setStreamingError] = useState<string | null>(null);

    // RAG 相关状态
    const [ragSources, setRagSources] = useState<Array<{label: string; title: string; sourceType: string; sourceUrl?: string | null; contentSnippet?: string}> | null>(null);
    const [ragFallback, setRagFallback] = useState<string | null>(null);

    // 编辑消息状态
    const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
    // TaskPlan ID（由后端意图识别触发 task_plan.created SSE 事件写入）
    const [activeTaskPlanId, setActiveTaskPlanId] = useState<string | null>(null);
    // 多 Agent 协作执行状态（由 multi_agent.status SSE 事件写入）
    const [multiAgentResult, setMultiAgentResult] = useState<MultiAgentRunResult | null>(null);

    // 机会横幅「一键创作」触发的 TaskPlan 也在此展示
    useEffect(() => {
        const handler = (e: Event) => {
            const detail = (e as CustomEvent).detail as { planId?: string };
            if (detail?.planId) setActiveTaskPlanId(detail.planId);
        };
        window.addEventListener("taskplan:created", handler);
        return () => window.removeEventListener("taskplan:created", handler);
    }, []);

    const messagesEndRef = useRef<HTMLDivElement>(null);

    // 流式请求的中断控制器：切换会话或卸载组件时必须 abort，
    // 否则旧流会继续向新会话的界面状态写入数据（串话 + 卸载后 setState）
    const abortRef = useRef<AbortController | null>(null);
    useEffect(() => {
        return () => {
            abortRef.current?.abort();
            abortRef.current = null;
        };
    }, [currentChatId]);

    // 切换会话时清空上一个会话遗留的流式状态（错误提示、半截文本等）
    useEffect(() => {
        setIsStreaming(false);
        setAgentStatus(null);
        setStreamingText("");
        setStreamingSourceList(null);
        setStreamingError(null);
        setRagSources(null);
        setRagFallback(null);
        setMultiAgentResult(null);
        setActiveTaskPlanId(null);
    }, [currentChatId]);

    // 获取消息历史
    const {data: messages = [], isLoading} = useQuery<Message[]>({
        queryKey: ["messages", currentChatId],
        queryFn: () => apiGet(`/api/chats/${currentChatId}/messages`),
        enabled: !!currentChatId,
    });

    // 0. 虚拟化关联父节点，使得历史线性对话正常链条化，避免 siblings 冲突
    const resolvedMessages = resolveParentIds(messages);

    // 1. 根据当前 activeLeafMessageId 溯源出当前渲染的分支路径，如果为空则初始化
    const getActivePathAndInit = (allMsgs: Message[]) => {
        if (allMsgs.length === 0) return {path: [], leafId: null};

        // 找出所有已被引用为 parentMessageId 的消息 ID
        const parentIdsSet = new Set(allMsgs.map(m => m.parentMessageId).filter(Boolean) as string[]);

        // 找出所有叶子节点（没有被任何消息作为 parentMessageId 引用的消息）
        const leafMessages = allMsgs.filter(m => !parentIdsSet.has(m.messageId));

        // 按创建时间降序排序，最新的叶子节点作为默认值
        leafMessages.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
        const defaultLeafId = leafMessages[0]?.messageId || null;

        let currentLeafId = activeLeafMessageId;
        if (!currentLeafId || !allMsgs.some(m => m.messageId === currentLeafId)) {
            currentLeafId = defaultLeafId;
        }

        if (!currentLeafId) return {path: [], leafId: null};

        const msgMap = new Map(allMsgs.map(m => [m.messageId, m]));
        const path: Message[] = [];
        let currId: string | null = currentLeafId;
        const visited = new Set<string>();

        while (currId && msgMap.has(currId) && !visited.has(currId)) {
            visited.add(currId);
            const currentMsg: Message = msgMap.get(currId)!;
            path.push(currentMsg);

            if (currentMsg.parentMessageId) {
                currId = currentMsg.parentMessageId;
            } else {
                // 时间顺序兜底逻辑：无 parentMessageId 且在时间线上有更早消息时，关联到前一个
                const sortedAll = [...allMsgs].sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
                const idx = sortedAll.findIndex(m => m.messageId === currentMsg.messageId);
                if (idx > 0) {
                    currId = sortedAll[idx - 1].messageId;
                } else {
                    currId = null;
                }
            }
        }

        path.reverse();
        return {path, leafId: currentLeafId};
    };

    const {path: activePath, leafId: calculatedLeafId} = getActivePathAndInit(resolvedMessages);

    // 2. 避免在渲染阶段直接调用 Zustand store 的 state setter
    useEffect(() => {
        if (calculatedLeafId && calculatedLeafId !== activeLeafMessageId) {
            setActiveLeafMessageId(calculatedLeafId);
        }
    }, [calculatedLeafId, activeLeafMessageId, setActiveLeafMessageId]);

    // 滚动到底部
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({behavior: "smooth"});
    }, [activePath, streamingText, agentStatus]);


    // ── 发送消息 ──
    const handleSendMessage = async (e?: React.FormEvent, overrideContent?: string, overrideParentId?: string | null) => {
        if (e) e.preventDefault();
        const content = (overrideContent !== undefined ? overrideContent : inputText).trim();
        if (!content || isStreaming) return;

        if (overrideContent === undefined) {
            setInputText("");
        }

        setIsStreaming(true);
        setStreamingText("");
        setAgentStatus("发送中...");
        setStreamingSourceList(null);
        setStreamingError(null);
        setRagSources(null);
        setRagFallback(null);
        // 新一轮对话：清掉上一次的 Agent 协作卡片，避免旧状态残留
        setMultiAgentResult(null);
        setActiveTaskPlanId(null);

        let activeChatId = currentChatId;
        if (!activeChatId) {
            try {
                const newChat = await apiPost<{ chatId: string; title: string }>("/api/chats", {title: "新对话"});
                activeChatId = newChat.chatId;
                setCurrentChatId(activeChatId);
                navigate(`/chat/${activeChatId}`);
                queryClient.invalidateQueries({queryKey: ["chats"]});
            } catch (err) {
                console.error("创建会话失败:", err);
                setStreamingError("初始化会话失败，请重试");
                setIsStreaming(false);
                return;
            }
        }

        // 确定父级消息 ID
        const parentMessageId = overrideParentId !== undefined ? overrideParentId : activeLeafMessageId;

        // 乐观更新：立即追加用户消息到列表
        queryClient.setQueryData<Message[]>(["messages", activeChatId], (prev = []) => [
            ...prev,
            {
                messageId: "temp-user-msg",
                role: "user",
                messageType: "text",
                content,
                parentMessageId: parentMessageId,
                payload: null,
                createdAt: new Date().toISOString(),
            },
        ]);

        // 立即更新 activeLeafMessageId 为 temp-user-msg，确保 getActivePathAndInit 能够将其追踪并渲染上屏
        setActiveLeafMessageId("temp-user-msg");

        const controller = new AbortController();
        abortRef.current = controller;

        try {
            await streamPost(`/api/chats/${activeChatId}/messages/stream`, {
                content,
                parentMessageId,
            }, {
                onEvent: (event, data) => {
                    if (event === "agent.status") {
                        const statusMap: Record<string, string> = {
                            routing_intent: "分析意图...",
                            generating: "生成回复中...",
                        };
                        setAgentStatus(statusMap[data.status] || data.status);
                    } else if (event === "tool.started") {
                        const toolMap: Record<string, string> = {
                            parse_url: "解析链接中...",
                            collect: "采集帖子中...",
                        };
                        setAgentStatus(toolMap[data.tool_type] || `执行工具: ${data.tool_type}`);
                    } else if (event === "task_plan.created") {
                        // 意图识别判定为复合任务：展示 TaskPlan 结果卡片
                        setAgentStatus("复合任务执行中...");
                        if (data?.planId) setActiveTaskPlanId(data.planId);
                    } else if (event === "multi_agent.status") {
                        // 意图识别判定为多 Agent 协作：展示 5 个子 Agent 状态
                        setAgentStatus("多 Agent 协作中...");
                        if (data?.status) {
                            setMultiAgentResult({
                                runId: data.runId || "chat-run",
                                status: data.status,
                                agents: data.agents || [],
                                finalContent: data.finalContent,
                            });
                        }
                    } else if (event === "message.delta") {
                        setAgentStatus(null);
                        setStreamingText((prev) => prev + data.delta);
                    } else if (event === "source.list.completed") {
                        setAgentStatus(null);
                        setStreamingSourceList(data);
                    } else if (event === "rag.sources") {
                        // RAG 私有资料来源
                        setRagSources(data.sources || []);
                        if (data.fallbackNotice) setRagFallback(data.fallbackNotice);
                    } else if (event === "rag.fallback") {
                        setRagFallback(data.reason || "私有资料证据不足，使用了其他知识来源");
                    } else if (event === "agent.error") {
                        setAgentStatus(null);
                        setStreamingError(data.message || "生成超时已自动停止，请重试");
                    } else if (event === "run.failed") {
                        setAgentStatus(null);
                        setStreamingError(data.message || "请求处理失败");
                    }
                },
                onError: (err) => {
                    setStreamingError(err.message);
                    setAgentStatus(null);
                },
            }, controller.signal);
        } catch (err) {
            // 主动中断静默返回；其余错误已由 onError 写入 streamingError
            if (!(err instanceof DOMException && err.name === "AbortError")) {
                console.error("流式请求失败:", err);
            }
        } finally {
            await refreshAfterStream(activeChatId, controller, true);
        }
    };

    const handleConfirmEdit = async (msg: Message, content: string) => {
        setEditingMessageId(null);
        await handleSendMessage(undefined, content, msg.parentMessageId);
    };

    // 流结束后统一清理并刷新消息历史；被中断说明用户已切换会话，不再刷新
    const refreshAfterStream = async (chatId: string, controller: AbortController, refreshFallback?: boolean) => {
        if (abortRef.current === controller) {
            abortRef.current = null;
        }
        setIsStreaming(false);
        setAgentStatus(null);
        setStreamingText("");
        setStreamingSourceList(null);
        setRagSources(null);
        setRagFallback(null);

        if (!controller.signal.aborted) {
            queryClient.invalidateQueries({ queryKey: ["chats"] });
            try {
                const updatedMessages = await queryClient.fetchQuery<Message[]>({
                    queryKey: ["messages", chatId],
                    queryFn: () => apiGet(`/api/chats/${chatId}/messages`),
                });
                if (updatedMessages.length > 0) {
                    setActiveLeafMessageId(updatedMessages[updatedMessages.length - 1].messageId);
                }
            } catch (refreshErr) {
                console.error("刷新消息历史失败:", refreshErr);
                queryClient.setQueryData<Message[]>(["messages", chatId], (prev = []) =>
                    prev.filter((m) => m.messageId !== "temp-user-msg"),
                );
                if (refreshFallback) {
                    setStreamingError((prev) => prev ?? "消息已发送，但刷新历史失败，请手动刷新");
                }
            }
        }
    };

    // Human-in-the-loop：用户点击选择卡片选项后，把选择提交到 /choices 并发起续跑（SSE 流式等待）
    const handleSelectChoice = async (optionId: string, messageId: string) => {
        if (isStreaming || !currentChatId) return;
        setIsStreaming(true);
        setStreamingText("");
        setAgentStatus("已选择，正在继续...");
        setStreamingError(null);

        const controller = new AbortController();
        abortRef.current = controller;

        try {
            await streamPost(`/api/chats/${currentChatId}/choices`, {
                messageId,
                selection: optionId,
            }, {
                onEvent: (event, data) => {
                    if (event === "agent.status") {
                        const statusMap: Record<string, string> = {
                            routing_intent: "分析意图...",
                            generating: "生成回复中...",
                        };
                        setAgentStatus(statusMap[data.status] || data.status);
                    } else if (event === "tool.started") {
                        const toolMap: Record<string, string> = {
                            parse_url: "解析链接中...",
                            collect: "采集帖子中...",
                        };
                        setAgentStatus(toolMap[data.tool_type] || `执行工具: ${data.tool_type}`);
                    } else if (event === "message.delta") {
                        setAgentStatus(null);
                        setStreamingText((prev) => prev + data.delta);
                    } else if (event === "agent.error") {
                        setAgentStatus(null);
                        setStreamingError(data.message || "生成超时已自动停止，请重试");
                    } else if (event === "run.failed") {
                        setAgentStatus(null);
                        setStreamingError(data.message || "续跑失败，请重试");
                    }
                },
                onError: (err) => {
                    setStreamingError(err.message);
                    setAgentStatus(null);
                },
            }, controller.signal);
        } catch (err) {
            if (!(err instanceof DOMException && err.name === "AbortError")) {
                console.error("提交选择失败:", err);
            }
        } finally {
            await refreshAfterStream(currentChatId, controller);
        }
    };

    const handleSwitchSibling = (msg: Message, direction: "prev" | "next") => {
        const siblings = resolvedMessages.filter(m => m.parentMessageId === msg.parentMessageId && m.role === "user");
        siblings.sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());

        const currentIndex = siblings.findIndex(s => s.messageId === msg.messageId);
        let targetIndex = currentIndex;
        if (direction === "prev" && currentIndex > 0) {
            targetIndex = currentIndex - 1;
        } else if (direction === "next" && currentIndex < siblings.length - 1) {
            targetIndex = currentIndex + 1;
        }

        if (targetIndex !== currentIndex) {
            const targetMsg = siblings[targetIndex];
            // 查找目标提问节点下游最深的叶子节点
            const findActiveLeafDescendant = (startId: string, allMsgs: Message[]): string => {
                let currentId = startId;
                while (true) {
                    const children = allMsgs.filter(m => m.parentMessageId === currentId);
                    if (children.length === 0) break;
                    children.sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
                    currentId = children[0].messageId;
                }
                return currentId;
            };
            const leafId = findActiveLeafDescendant(targetMsg.messageId, resolvedMessages);
            setActiveLeafMessageId(leafId);
        }
    };

    if (!currentChatId) {
        return (
            <div
                className="flex flex-col flex-1 bg-zinc-50/50 dark:bg-zinc-950/20 items-center justify-center p-6 select-none overflow-y-auto min-h-0">
                <div className="max-w-2xl w-full flex flex-col items-center gap-6 my-auto">
                    {/* Logo & Title */}
                    <div className="flex flex-col items-center gap-3">
                        <div
                            className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-500 text-white shadow-md shadow-indigo-500/20">
                            <Sparkles className="h-6 w-6"/>
                        </div>
                        <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-100 flex items-center gap-2 mt-1">
                            欢迎使用超级大脑，请开启你的对话
                        </h1>
                    </div>

                    {/* Centered Input Container */}
                    <div className="w-full">
                        <PromptInput
                            value={inputText}
                            onChange={setInputText}
                            onSubmit={handleSendMessage}
                            placeholder="粘贴链接或输入采集主题..."
                            disabled={isStreaming}
                        />
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-muted/30">
            {/* ── 消息列表 ── */}
            <ScrollArea className="flex-1 min-h-0 p-4">
                <div className="flex w-full flex-col gap-4 px-2">
                    {isLoading ? (
                        <div className="space-y-3 py-8">
                            <Skeleton className="mx-auto h-16 w-3/4 rounded-xl"/>
                            <Skeleton className="ml-auto h-10 w-1/2 rounded-xl"/>
                            <Skeleton className="h-16 w-3/4 rounded-xl"/>
                        </div>
                    ) : (
                        activePath.map((msg) => {
                            const siblings = resolvedMessages.filter(m => m.parentMessageId === msg.parentMessageId && m.role === "user");
                            siblings.sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());

                            return (
                                <MessageBubble
                                    key={msg.messageId}
                                    msg={msg}
                                    onSelectItem={setSelectedSourceItemId}
                                    onSelectChoice={handleSelectChoice}
                                    selectedId={selectedSourceItemId}
                                    isEditing={editingMessageId === msg.messageId}
                                    onStartEdit={() => setEditingMessageId(msg.messageId)}
                                    onCancelEdit={() => setEditingMessageId(null)}
                                    onConfirmEdit={(content) => handleConfirmEdit(msg, content)}
                                    siblings={siblings}
                                    onSwitchSibling={(dir) => handleSwitchSibling(msg, dir)}
                                    isStreaming={isStreaming}
                                />
                            );
                        })
                    )}

                    {/* 实时流式响应；出错后卡片保留展示错误，直到下一次发送 */}
                    {(isStreaming || streamingError) && (
                        <div className="flex justify-start w-full">
                            <Card className="max-w-[calc(100%-3rem)] w-full border-none bg-card shadow-sm">
                                <CardContent className="p-3.5">
                                    {agentStatus && (
                                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                            <Loader2 className="h-4 w-4 animate-spin text-primary"/>
                                            {agentStatus}
                                        </div>
                                    )}
                                    {streamingText && (
                                        <div className="text-sm leading-relaxed max-w-none text-foreground/90">
                                            <ReactMarkdown
                                                remarkPlugins={[remarkGfm]}
                                                components={getMarkdownComponents(false)}
                                            >
                                                {streamingText}
                                            </ReactMarkdown>
                                        </div>
                                    )}
                                    {streamingSourceList && (
                                        <SourceListCard
                                            data={streamingSourceList}
                                            onSelectItem={setSelectedSourceItemId}
                                            selectedId={selectedSourceItemId}
                                        />
                                    )}
                                    {streamingError && (
                                        <div
                                            className="flex items-start gap-2.5 text-destructive bg-destructive/5 border border-destructive/20 rounded-xl p-3 w-full">
                                            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5"/>
                                            <div>
                                                <p className="text-sm font-semibold">请求出错</p>
                                                <p className="mt-1 text-xs leading-relaxed opacity-90">{streamingError}</p>
                                            </div>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    )}
                    <div ref={messagesEndRef}/>
                </div>
            </ScrollArea>

            {/* ── TaskPlan 进度卡片（如果当前 chat 创建过 plan）── */}
            {activeTaskPlanId && <TaskPlanCard planId={activeTaskPlanId} />}

            {/* ── Phase 4 Agent 协作执行状态卡片（由后端意图识别触发，无独立输入框）── */}
            {multiAgentResult && (
                <AgentWorkspacePanel
                    goal=""
                    running={multiAgentResult.status === "running" || multiAgentResult.status === "pending"}
                    result={multiAgentResult}
                />
            )}

            {/* ── 底部输入框 ── */}
            <div className="shrink-0 border-t bg-card p-4 fixed-bottom-input-area">
                <div className="flex items-center gap-2 mb-2">
                    <MemoryAppliedBadge />
                </div>
                <PromptInput
                    value={inputText}
                    onChange={setInputText}
                    onSubmit={() => handleSendMessage()}
                    placeholder="粘贴链接或输入采集主题..."
                    disabled={isStreaming}
                />
            </div>
        </div>
    );
}

// ── 消息气泡 ──────────────────────────────────────────────────────

/** 单条消息渲染；按角色区分气泡方向和样式，支持内联编辑、复制、多版本切换 */
function MessageBubble({
                           msg,
                           onSelectItem,
                           onSelectChoice,
                           selectedId,
                           isEditing,
                           onStartEdit,
                           onCancelEdit,
                           onConfirmEdit,
                           siblings,
                           onSwitchSibling,
                           isStreaming,
                       }: {
    msg: Message;
    onSelectItem: (id: string) => void;
    onSelectChoice: (optionId: string, messageId: string) => void;
    selectedId: string | null;
    isEditing: boolean;
    onStartEdit: () => void;
    onCancelEdit: () => void;
    onConfirmEdit: (content: string) => void;
    siblings: Message[];
    onSwitchSibling: (direction: "prev" | "next") => void;
    isStreaming: boolean;
}) {
    const isUser = msg.role === "user";
    const [editText, setEditText] = useState(msg.content || "");
    const [copied, setCopied] = useState(false);

    // 当进入编辑模式时，同步原消息内容
    useEffect(() => {
        if (isEditing) {
            setEditText(msg.content || "");
        }
    }, [isEditing, msg.content]);

    const handleCopy = async () => {
        if (!msg.content) return;
        try {
            await navigator.clipboard.writeText(msg.content);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch (err) {
            console.error("Failed to copy text: ", err);
        }
    };

    // 如果处于编辑模式下，展示圆角蓝色边框的内联编辑区域
    if (isEditing) {
        return (
            <div className={cn("flex w-full mb-3", isUser ? "justify-end" : "justify-start")}>
                <div
                    className="w-[85%] border border-blue-500 rounded-2xl p-3 bg-card shadow-sm flex flex-col gap-2.5 animate-in fade-in slide-in-from-bottom-2 duration-200">
                    <Textarea
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        placeholder="编辑您的问题..."
                        className="w-full min-h-[60px] bg-transparent resize-none border-none outline-none focus-visible:ring-0 focus-visible:ring-offset-0 p-0 text-sm focus:outline-none"
                        autoFocus
                    />
                    <div className="flex justify-end gap-2 shrink-0">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onCancelEdit}
                            className="rounded-full px-4 h-7 text-xs border border-muted bg-transparent hover:bg-muted/10 text-foreground"
                        >
                            取消
                        </Button>
                        <Button
                            size="sm"
                            onClick={() => onConfirmEdit(editText)}
                            disabled={isStreaming || !editText.trim()}
                            className="rounded-full px-4 h-7 text-xs bg-blue-600 hover:bg-blue-700 text-white"
                        >
                            发送
                        </Button>
                    </div>
                </div>
            </div>
        );
    }

    // 1. 如果是工具执行状态类型消息，渲染微型技术感工具日志条
    if (msg.messageType === "tool_status") {
        return (
            <div className="flex w-full justify-start mb-2 px-2">
                <div
                    className="flex items-center gap-2 rounded-xl border border-border/30 bg-muted/20 px-3 py-1.5 text-xs text-muted-foreground select-none">
                    <Wrench className="h-3.5 w-3.5 text-amber-500 shrink-0"/>
                    <span>
            执行工具: <code
                        className="font-mono bg-muted/60 px-1 py-0.5 rounded text-[11px] border border-border/20">{msg.payload?.tool_type || msg.content}</code>
          </span>
                    {msg.payload?.status === "completed" || !isStreaming ? (
                        <Badge variant="outline"
                               className="text-[10px] py-0 h-4 px-1.5 text-emerald-500 border-emerald-500/20 bg-emerald-500/5">已完成</Badge>
                    ) : (
                        <Badge variant="outline"
                               className="text-[10px] py-0 h-4 px-1.5 text-amber-500 border-amber-500/20 bg-amber-500/5 animate-pulse">运行中</Badge>
                    )}
                </div>
            </div>
        );
    }

    return (
        <div className={cn("flex w-full mb-2", isUser ? "justify-end" : "justify-start")}>
            <div
                className={cn(
                    "flex flex-col gap-1",
                    isUser ? "max-w-[85%] items-end" : "max-w-[calc(100%-3rem)] w-full items-start mr-auto"
                )}
            >
                <Card
                    className={cn(
                        "border-none shadow-sm",
                        isUser ? "bg-primary text-primary-foreground" : "bg-card w-full",
                    )}
                >
                    <CardContent className="p-3.5">
                        {msg.messageType === "text" && (
                            <div
                                className={cn("text-sm leading-relaxed max-w-none", isUser ? "text-primary-foreground" : "text-foreground/90")}>
                                <ReactMarkdown
                                    remarkPlugins={[remarkGfm]}
                                    components={getMarkdownComponents(isUser)}
                                >
                                    {msg.content || ""}
                                </ReactMarkdown>
                                {/* RAG 私有资料来源展示 */}
                                {!isUser && msg.payload?.ragSources && (
                                    <SourceList
                                        sources={msg.payload.ragSources}
                                        fallbackNotice={msg.payload.ragFallback}
                                        traceId={msg.payload.traceId}
                                    />
                                )}
                            </div>
                        )}
                        {msg.messageType === "error" && (
                            <div
                                className="flex items-start gap-2.5 text-destructive bg-destructive/5 border border-destructive/20 rounded-xl p-3 w-full animate-in fade-in slide-in-from-bottom-2 duration-200">
                                <AlertCircle className="h-5 w-5 shrink-0 mt-0.5"/>
                                <div>
                                    <p className="text-sm font-semibold">请求出错</p>
                                    <p className="mt-1 text-xs leading-relaxed opacity-90">{msg.payload?.message || msg.content}</p>
                                </div>
                            </div>
                        )}
                        {msg.messageType === "source_list" && (
                            <SourceListCard
                                data={msg.payload || msg.content}
                                onSelectItem={onSelectItem}
                                selectedId={selectedId}
                            />
                        )}
                        {msg.messageType === "choice_request" && (
                            <ChoiceRequestCard
                                payload={msg.payload || {}}
                                messageId={msg.messageId}
                                onSelect={onSelectChoice}
                            />
                        )}
                        {msg.messageType === "source_card" && (
                            <SourceCardView
                                data={msg.payload || msg.content}
                                onSelectItem={onSelectItem}
                                selectedId={selectedId}
                            />
                        )}
                    </CardContent>
                </Card>

                {/* ── 复制、编辑、分支切换操作栏 ── */}
                {!isStreaming && (
                    <div
                        className={cn("flex items-center gap-2.5 px-2.5 mt-0.5 text-xs text-muted-foreground/60 select-none")}>
                        {/* 复制按钮 */}
                        <button
                            onClick={handleCopy}
                            className="cursor-pointer hover:text-muted-foreground transition-colors p-0.5"
                            title="复制文本"
                        >
                            {copied ? (
                                <Check
                                    className="h-3.5 w-3.5 text-emerald-500 animate-in fade-in zoom-in-50 duration-200"/>
                            ) : (
                                <Copy className="h-3.5 w-3.5"/>
                            )}
                        </button>

                        {/* 编辑按钮（仅限 user 消息） */}
                        {isUser && (
                            <button
                                onClick={onStartEdit}
                                className="cursor-pointer hover:text-muted-foreground transition-colors p-0.5"
                                title="编辑提问"
                            >
                                <Pencil className="h-3.5 w-3.5"/>
                            </button>
                        )}

                        {/* 版本切换（仅限存在多个 siblings 的 user 消息） */}
                        {isUser && siblings.length > 1 && (
                            <div className="flex items-center gap-1 border-l pl-2.5 ml-1 border-muted-foreground/20">
                                <button
                                    onClick={() => onSwitchSibling("prev")}
                                    disabled={siblings.findIndex(s => s.messageId === msg.messageId) === 0}
                                    className="cursor-pointer hover:text-muted-foreground transition-colors p-0.5 disabled:opacity-30 disabled:cursor-not-allowed"
                                >
                                    <ChevronLeft className="h-3.5 w-3.5"/>
                                </button>
                                <span className="text-[11px] font-medium min-w-[28px] text-center">
                  {siblings.findIndex(s => s.messageId === msg.messageId) + 1} / {siblings.length}
                </span>
                                <button
                                    onClick={() => onSwitchSibling("next")}
                                    disabled={siblings.findIndex(s => s.messageId === msg.messageId) === siblings.length - 1}
                                    className="cursor-pointer hover:text-muted-foreground transition-colors p-0.5 disabled:opacity-30 disabled:cursor-not-allowed"
                                >
                                    <ChevronRight className="h-3.5 w-3.5"/>
                                </button>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Human-in-the-loop 选择卡片 ───────────────────────────────────────

/** 渲染 Agent 的选择请求；用户点击选项后把选择提交到 /choices 并发起续跑 */
function ChoiceRequestCard({
                               payload,
                               messageId,
                               onSelect,
                           }: {
    payload: any;
    messageId: string;
    onSelect: (optionId: string, messageId: string) => void;
}) {
    const options: Array<{ id: string; label: string; description?: string }> = payload?.options || [];
    if (options.length === 0) return null;
    return (
        <div className="mt-1 rounded-xl border border-amber-300/50 dark:border-amber-700/40 bg-amber-50/40 dark:bg-amber-950/10 p-3">
            <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">{payload?.question || "需要你选择一个处理方式："}</p>
            <div className="mt-2 flex flex-col gap-1.5">
                {options.map((opt) => (
                    <button
                        key={opt.id}
                        onClick={() => onSelect(opt.id, messageId)}
                        className="text-left text-xs px-3 py-2 rounded-lg border border-amber-200 dark:border-amber-800/50 bg-white/60 dark:bg-zinc-900/40 hover:bg-amber-100/60 dark:hover:bg-amber-900/20 transition-colors"
                    >
                        <span className="font-medium text-amber-900 dark:text-amber-200">{opt.label}</span>
                        {opt.description && (
                            <span className="block text-[10px] text-muted-foreground mt-0.5">{opt.description}</span>
                        )}
                    </button>
                ))}
            </div>
        </div>
    );
}

// ── 采集结果卡片列表 ──────────────────────────────────────────────

/** 渲染 Agent 返回的帖子列表；点击帖子选中后，右侧编辑面板加载对应文档 */
function SourceListCard({
                            data,
                            onSelectItem,
                            selectedId,
                        }: {
    data: any;
    onSelectItem: (id: string) => void;
    selectedId: string | null;
}) {
    const items = data?.items || [];
    const toolType = data?.tool_type || "parse_url";

    return (
        <div className="space-y-3">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                {toolType === "parse_url" ? (
                    <>
                        <Globe className="h-4 w-4 text-emerald-500"/>
                        解析到以下帖子内容：
                    </>
                ) : (
                    <>
                        <Sparkles className="h-4 w-4 text-amber-500"/>
                        为您搜索采集到以下主题帖子：
                    </>
                )}
            </div>

            <div className="grid gap-2.5">
                {items.map((item: any, idx: number) => {
                    const itemId = item.id || item.externalId || `item-${idx}`;
                    return (
                        <Card
                            key={itemId}
                            onClick={() => onSelectItem(itemId)}
                            className={cn(
                                "cursor-pointer transition-all hover:shadow-sm",
                                selectedId === itemId ? "border-primary/50 bg-primary/5" : "hover:border-muted-foreground/30",
                            )}
                        >
                            <CardContent className="p-3">
                                <h4 className="mb-1 truncate text-sm font-semibold">{item.title}</h4>
                                {item.summary && (
                                    <p className="mb-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                                        {item.summary}
                                    </p>
                                )}
                                <div className="flex items-center gap-2 text-[10px] text-muted-foreground mb-2 flex-wrap">
                                    {item.publishedAt && (
                                        <span className="inline-flex items-center gap-1">
                                            <Clock className="h-3 w-3"/>
                                            {item.publishedAt}
                                        </span>
                                    )}
                                    {item.metrics?.likes && (
                                        <span className="inline-flex items-center gap-1">
                                            <Sparkles className="h-3 w-3 text-amber-500"/>
                                            {item.metrics.likes}
                                        </span>
                                    )}
                                    {item.author && <span>作者：{item.author}</span>}
                                </div>
                                <div className="flex items-center justify-between">
                                    <Badge variant="secondary" className="text-[10px] uppercase">
                                        {item.platform || "zhihu"}
                                    </Badge>
                                    <span
                                        className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-primary">
                    <FileText className="h-3 w-3"/>
                    开始创作回答
                  </span>
                                </div>
                            </CardContent>
                        </Card>
                    );
                })}
            </div>
        </div>
    );
}

/** 渲染单篇源文章详情卡片 */
function SourceCardView({
                            data,
                            onSelectItem,
                            selectedId,
                        }: {
    data: any;
    onSelectItem: (id: string) => void;
    selectedId: string | null;
}) {
    let item = data;
    if (typeof data === "string") {
        try {
            item = JSON.parse(data);
        } catch {
            item = {};
        }
    }

    const itemId = item?.id || item?.externalId || "source-card-item";
    return (
        <div className="space-y-2.5">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                <Globe className="h-4 w-4 text-emerald-500"/>
                解析到以下帖子内容：
            </div>
            <Card
                onClick={() => onSelectItem(itemId)}
                className={cn(
                    "cursor-pointer transition-all hover:shadow-sm w-full",
                    selectedId === itemId ? "border-primary/50 bg-primary/5" : "hover:border-muted-foreground/30",
                )}
            >
                <CardContent className="p-3.5">
                    <h4 className="mb-1 truncate text-sm font-semibold">{item?.title || "未知标题"}</h4>
                    {item?.summary && (
                        <p className="mb-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                            {item.summary}
                        </p>
                    )}
                    <div className="flex items-center justify-between">
                        <Badge variant="secondary" className="text-[10px] uppercase">
                            {item?.platform || "zhihu"}
                        </Badge>
                        <span
                            className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-primary transition-colors">
              <FileText className="h-3 w-3"/>
              开始创作回答
            </span>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
