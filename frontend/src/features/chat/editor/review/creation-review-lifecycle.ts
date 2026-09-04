export type CreationProgressState = {
  running: boolean;
  label: string;
  iteration: number;
  maxIterations: number;
  score: number | null;
};

export const initialCreationProgress: CreationProgressState = {
  running: false,
  label: "",
  iteration: 0,
  maxIterations: 0,
  score: null,
};

function numberValue(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function reduceCreationProgress(
  state: CreationProgressState,
  event: string,
  data: Record<string, unknown>,
): CreationProgressState {
  switch (event) {
    case "run.started":
      return {
        ...state,
        running: true,
        label: "正在生成内容",
        iteration: 0,
        maxIterations: numberValue(data.maxIterations, state.maxIterations),
        score: null,
      };
    case "writer.progress": {
      const label = typeof data.label === "string" ? data.label : state.label;
      const status = data.status === "failed" ? "failed" : data.status;
      return {
        ...state,
        running: status === "failed" ? false : true,
        label: status === "failed" ? "创作失败" : label,
      };
    }
    case "review.started": {
      const iteration = numberValue(data.iteration, state.iteration);
      const maxIterations = numberValue(data.maxIterations, state.maxIterations);
      return {
        ...state,
        running: true,
        label: `正在进行第 ${iteration}/${maxIterations} 轮评审`,
        iteration,
        maxIterations,
      };
    }
    case "review.completed": {
      const passed = data.passed === true;
      const score =
        typeof data.overallScore === "number" && Number.isFinite(data.overallScore)
          ? data.overallScore
          : state.score;
      return {
        ...state,
        running: true,
        label: passed ? "评审已通过，正在保存最终内容" : "评审完成，正在准备优化",
        iteration: numberValue(data.iteration, state.iteration),
        score,
      };
    }
    case "rewrite.started":
      return {
        ...state,
        running: true,
        label: "未达到质量阈值，正在根据建议优化",
        iteration: numberValue(data.iteration, state.iteration),
        maxIterations: numberValue(data.maxIterations, state.maxIterations),
      };
    case "document.completed":
      return { ...state, running: true, label: "正在保存最终内容" };
    case "run.completed":
      return { ...state, running: false, label: "创作完成" };
    case "run.failed":
      return { ...state, running: false, label: "创作失败" };
    default:
      return state;
  }
}
