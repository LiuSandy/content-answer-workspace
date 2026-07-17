import { create } from "zustand";

type ChatState = {
  currentChatId: string | null;
  selectedSourceItemId: string | null;
  activeLeafMessageId: string | null;
  setCurrentChatId: (id: string | null) => void;
  setSelectedSourceItemId: (id: string | null) => void;
  setActiveLeafMessageId: (id: string | null) => void;
};

export const useChatStore = create<ChatState>((set) => ({
  currentChatId: null,
  selectedSourceItemId: null,
  activeLeafMessageId: null,
  setCurrentChatId: (id) =>
    set({
      currentChatId: id,
      selectedSourceItemId: null, // 切换 Chat 或关闭时重置选中的帖子
      activeLeafMessageId: null, // 重置活跃叶子消息 ID
    }),
  setSelectedSourceItemId: (id) => set({ selectedSourceItemId: id }),
  setActiveLeafMessageId: (id) => set({ activeLeafMessageId: id }),
}));
