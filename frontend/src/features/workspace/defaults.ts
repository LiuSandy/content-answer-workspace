import { DEFAULT_PLATFORM } from "@/types/workflow";

export const supportedPlatforms = [
  {
    id: DEFAULT_PLATFORM,
    label: "知乎",
  },
  {
    id: "xiaohongshu",
    label: "小红书",
  },
] as const;

export const defaultPlatform = supportedPlatforms[0].id;
export const maxCollectCount = 100;

