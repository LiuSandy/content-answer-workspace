export interface AgentStatus {
  name: string;
  status: string;
  message?: string;
  resultPreview?: string;
}

export interface MultiAgentRunResult {
  runId: string;
  status: string;
  agents: AgentStatus[];
  finalContent?: string;
}
