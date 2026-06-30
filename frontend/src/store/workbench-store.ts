import { create } from "zustand";

import type { Platform, WorkbenchItem } from "@/types/workflow";

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
  setStatusFilter: (f: StatusFilter) => void;
  setPlatformFilter: (p: PlatformFilter) => void;
  setSearchKeyword: (kw: string) => void;
  setIsGenerating: (v: boolean) => void;
  setGlobalPromptConfig: (config: Partial<GlobalPromptConfig>) => void;
};

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
    const toAdd = newItems.filter((i) => !existingIds.has(i.id));
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
      items: state.items.map((i) => (i.id === id ? { ...i, answer } : i)),
    })),

  setItem: (id, item) =>
    set((state) => ({
      items: state.items.map((i) => (i.id === id ? item : i)),
    })),

  setStatusFilter: (statusFilter) => set({ statusFilter }),
  setPlatformFilter: (platformFilter) => set({ platformFilter }),
  setSearchKeyword: (searchKeyword) => set({ searchKeyword }),
  setIsGenerating: (isGenerating) => set({ isGenerating }),
  setGlobalPromptConfig: (config) =>
    set((state) => ({ globalPromptConfig: { ...state.globalPromptConfig, ...config } })),
}));
