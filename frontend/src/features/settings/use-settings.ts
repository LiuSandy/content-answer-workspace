/**
 * 设置相关 TanStack Query hooks；单独定义是为了让各配置分区组件共用同一套缓存和失效逻辑。
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CollectConfig,
  LlmConfig,
  PromptsConfig,
  PublishConfig,
  TopicItem,
  configureGroqKey,
  createTopic,
  deleteTopic,
  getAgentReachStatus,
  getSettings,
  getTopics,
  getTwitterAuth,
  saveTwitterAuth,
  updateAgentReachPlatforms,
  updateCollectSettings,
  updateLlmSettings,
  updatePromptsSettings,
  updatePublishSettings,
  updateTopic,
} from "./settings-api";

export const SETTINGS_QUERY_KEY = ["settings"];
export const TOPICS_QUERY_KEY = ["settings-topics"];
export const AGENT_REACH_STATUS_QUERY_KEY = ["agent-reach-status"];
export const TWITTER_AUTH_QUERY_KEY = ["agent-reach-twitter-auth"];

export function useSettings() {
  return useQuery({
    queryKey: SETTINGS_QUERY_KEY,
    queryFn: getSettings,
    staleTime: 30_000,
  });
}

export function useTopics() {
  return useQuery({
    queryKey: TOPICS_QUERY_KEY,
    queryFn: getTopics,
    staleTime: 30_000,
  });
}

export function useAgentReachStatus() {
  return useQuery({
    queryKey: AGENT_REACH_STATUS_QUERY_KEY,
    queryFn: getAgentReachStatus,
    staleTime: 10_000,
    retry: false,
  });
}

export function useUpdateLlm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { baseUrl: string; model: string; apiKey?: string }) =>
      updateLlmSettings(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY }),
  });
}

export function useUpdateCollect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<CollectConfig>) => updateCollectSettings(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY }),
  });
}

export function useUpdatePublish() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<PublishConfig>) => updatePublishSettings(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY }),
  });
}

export function useUpdatePrompts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<PromptsConfig>) => updatePromptsSettings(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY }),
  });
}

export function useUpdateAgentReachPlatforms() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (platforms: string[]) => updateAgentReachPlatforms(platforms),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY }),
  });
}

export function useConfigureGroqKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => configureGroqKey(key),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY }),
  });
}

export function useCreateTopic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (topic: TopicItem) => createTopic(topic),
    onSuccess: () => qc.invalidateQueries({ queryKey: TOPICS_QUERY_KEY }),
  });
}

export function useUpdateTopic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, topic }: { id: string; topic: TopicItem }) => updateTopic(id, topic),
    onSuccess: () => qc.invalidateQueries({ queryKey: TOPICS_QUERY_KEY }),
  });
}

export function useDeleteTopic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (topicId: string) => deleteTopic(topicId),
    onSuccess: () => qc.invalidateQueries({ queryKey: TOPICS_QUERY_KEY }),
  });
}

export function useTwitterAuth() {
  return useQuery({
    queryKey: TWITTER_AUTH_QUERY_KEY,
    queryFn: getTwitterAuth,
    staleTime: 30_000,
  });
}

export function useSaveTwitterAuth() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ authToken, ct0 }: { authToken: string; ct0: string }) =>
      saveTwitterAuth(authToken, ct0),
    onSuccess: () => qc.invalidateQueries({ queryKey: TWITTER_AUTH_QUERY_KEY }),
  });
}
