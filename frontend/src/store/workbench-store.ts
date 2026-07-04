import { create } from "zustand";

import type { GenerationStatus, GenerationUiStatus, Platform, WorkbenchItem } from "@/types/workflow";

export type StatusFilter = "all" | "pending" | "done";
export type PlatformFilter = Platform | "all";

export type GlobalPromptConfig = {
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
};

type WorkbenchState = {
  items: WorkbenchItem[];
  selectedItemId: string | null;
  statusFilter: StatusFilter;
  platformFilter: PlatformFilter;
  searchKeyword: string;
  isGenerating: boolean;
  globalPromptConfig: GlobalPromptConfig;

  /** 批量加入，按 id 去重，返回实际加入和跳过的数量。 */
  addItems: (items: WorkbenchItem[]) => { added: number; skipped: number };
  removeItem: (id: string) => void;
  selectItem: (id: string | null) => void;
  updateItemAnswer: (id: string, answer: string) => void;
  setItem: (id: string, item: WorkbenchItem) => void;
  setItemGenerationStatus: (id: string, status: GenerationStatus, error?: string) => void;
  startItemGenerationJob: (id: string, jobId: string) => void;
  restoreItemGenerationJob: (
    id: string,
    job: { jobId: string; status: GenerationUiStatus; lastEventId: number; streamingAnswer: string; error?: string | null },
  ) => void;
  appendItemStreamingAnswer: (id: string, text: string, eventId: number) => void;
  finishItemGenerationJob: (id: string, item: WorkbenchItem, eventId: number) => void;
  failItemGenerationJob: (id: string, message: string, eventId?: number) => void;
  interruptItemGenerationJob: (id: string, message: string) => void;
  cancelItemGenerationJob: (id: string, message?: string, eventId?: number) => void;
  setStatusFilter: (f: StatusFilter) => void;
  setPlatformFilter: (p: PlatformFilter) => void;
  setSearchKeyword: (kw: string) => void;
  setIsGenerating: (v: boolean) => void;
  setGlobalPromptConfig: (config: Partial<GlobalPromptConfig>) => void;
};

function mergeWorkbenchItem(current: WorkbenchItem, next: WorkbenchItem): WorkbenchItem {
  return {
    ...current,
    ...next,
    addedAt: current.addedAt,
    sourcePlatform: current.sourcePlatform,
    sourceTopic: current.sourceTopic,
    promptConfig: current.promptConfig,
  };
}

export const useWorkbenchStore = create<WorkbenchState>((set, get) => ({
  items: [],
  selectedItemId: null,
  statusFilter: "all",
  platformFilter: "all",
  searchKeyword: "",
  isGenerating: false,
  globalPromptConfig: { answerStyle: "", systemPrompt: "", generationPrompt: "" },

  addItems: (newItems) => {
    const existingIds = new Set(get().items.map((i) => i.id));
    const toAdd = newItems
      .filter((i) => !existingIds.has(i.id))
      .map((item) => ({ ...item, generationStatus: item.generationStatus ?? "idle" as const }));
    set((state) => ({ items: [...toAdd, ...state.items] }));
    return { added: toAdd.length, skipped: newItems.length - toAdd.length };
  },

  removeItem: (id) =>
    set((state) => ({
      items: state.items.filter((i) => i.id !== id),
      selectedItemId: state.selectedItemId === id ? null : state.selectedItemId,
    })),

  selectItem: (selectedItemId) => set({ selectedItemId }),

  updateItemAnswer: (id, answer) =>
    set((state) => ({
      items: state.items.map((i) =>
        i.id === id
          ? {
              ...i,
              answer,
              generationJob: i.generationJob
                ? { ...i.generationJob, draftAnswer: answer }
                : i.generationJob,
            }
          : i,
      ),
    })),

  setItem: (id, item) =>
    set((state) => ({
      items: state.items.map((i) => (i.id === id ? item : i)),
    })),

  setItemGenerationStatus: (id, generationStatus, generationError) =>
    set((state) => ({
      items: state.items.map((i) =>
        i.id === id
          ? {
              ...i,
              generationStatus,
              generationError:
                generationStatus === "error" || generationStatus === "interrupted"
                  ? generationError
                  : undefined,
            }
          : i,
      ),
    })),

  startItemGenerationJob: (id, jobId) =>
    set((state) => ({
      items: state.items.map((i) =>
        i.id === id
          ? {
              ...i,
              generationStatus: "generating",
              generationError: undefined,
              generationJob: {
                jobId,
                status: "generating",
                lastEventId: 0,
                streamingAnswer: "",
                finalAnswer: "",
                draftAnswer: i.answer || "",
                error: null,
              },
            }
          : i,
      ),
    })),

  restoreItemGenerationJob: (id, job) =>
    set((state) => ({
      items: state.items.map((i) =>
        i.id === id
          ? {
              ...i,
              generationStatus: job.status,
              generationError:
                job.status === "error" || job.status === "interrupted"
                  ? job.error || undefined
                  : undefined,
              generationJob: {
                jobId: job.jobId,
                status: job.status,
                lastEventId: job.lastEventId,
                streamingAnswer: job.streamingAnswer,
                finalAnswer: i.generationJob?.finalAnswer || i.answer || "",
                draftAnswer: i.generationJob?.draftAnswer || i.answer || "",
                error: job.error ?? null,
              },
            }
          : i,
      ),
    })),

  appendItemStreamingAnswer: (id, text, eventId) =>
    set((state) => ({
      items: state.items.map((i) => {
        if (i.id !== id || !i.generationJob || eventId <= i.generationJob.lastEventId) return i;
        return {
          ...i,
          generationJob: {
            ...i.generationJob,
            lastEventId: eventId,
            streamingAnswer: i.generationJob.streamingAnswer + text,
          },
        };
      }),
    })),

  finishItemGenerationJob: (id, item, eventId) =>
    set((state) => ({
      items: state.items.map((i) => {
        if (i.id !== id) return i;
        const merged = mergeWorkbenchItem(i, item);
        return {
          ...merged,
          generationStatus: "done",
          generationError: undefined,
          generationJob: {
            jobId: i.generationJob?.jobId || "",
            status: "done",
            lastEventId: eventId,
            streamingAnswer: i.generationJob?.streamingAnswer || item.answer || "",
            finalAnswer: item.answer || "",
            draftAnswer: item.answer || "",
            error: null,
          },
        };
      }),
    })),

  failItemGenerationJob: (id, message, eventId) =>
    set((state) => ({
      items: state.items.map((i) =>
        i.id === id
          ? {
              ...i,
              generationStatus: "error",
              generationError: message,
              generationJob: i.generationJob
                ? {
                    ...i.generationJob,
                    status: "error",
                    lastEventId: eventId ?? i.generationJob.lastEventId,
                    error: message,
                  }
                : i.generationJob,
            }
          : i,
      ),
    })),

  interruptItemGenerationJob: (id, message) =>
    set((state) => ({
      items: state.items.map((i) =>
        i.id === id
          ? {
              ...i,
              generationStatus: "interrupted",
              generationError: message,
              generationJob: i.generationJob
                ? { ...i.generationJob, status: "interrupted", error: message }
                : i.generationJob,
            }
          : i,
      ),
    })),

  cancelItemGenerationJob: (id, message = "生成已取消", eventId) =>
    set((state) => ({
      items: state.items.map((i) =>
        i.id === id
          ? {
              ...i,
              generationStatus: "canceled",
              generationError: undefined,
              generationJob: i.generationJob
                ? {
                    ...i.generationJob,
                    status: "canceled",
                    lastEventId: eventId ?? i.generationJob.lastEventId,
                    error: message,
                  }
                : i.generationJob,
            }
          : i,
      ),
    })),

  setStatusFilter: (statusFilter) => set({ statusFilter }),
  setPlatformFilter: (platformFilter) => set({ platformFilter }),
  setSearchKeyword: (searchKeyword) => set({ searchKeyword }),
  setIsGenerating: (isGenerating) => set({ isGenerating }),
  setGlobalPromptConfig: (config) =>
    set((state) => ({ globalPromptConfig: { ...state.globalPromptConfig, ...config } })),
}));
