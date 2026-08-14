import { useQuery } from "@tanstack/react-query";

export interface Opportunity {
  id: string;
  platform: string;
  questionTitle: string;
  questionUrl: string;
  hotScore: number;
  matchScore: number;
  opportunityScore: number;
  existingAnswerCount: number;
  scannedAt: string;
}

interface OpportunitiesResponse {
  ok: boolean;
  data: Opportunity[];
}

async function fetchOpportunities(workspaceId = "default"): Promise<Opportunity[]> {
  const res = await fetch(`/api/opportunities?workspaceId=${encodeURIComponent(workspaceId)}&limit=3`);
  const json: OpportunitiesResponse = await res.json();
  return json.data || [];
}

async function startPlan(opportunityId: string) {
  const res = await fetch(`/api/opportunities/${opportunityId}/start-plan`, { method: "POST" });
  return res.json();
}

export { fetchOpportunities, startPlan };