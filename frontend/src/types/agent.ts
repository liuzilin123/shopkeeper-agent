/**
 * 智能体类型定义
 * 定义问数智能体前端使用的 SSE 事件、流程步骤和聊天消息类型
 */
export type ProgressStatus = "running" | "success" | "error";

export type ProgressEvent = {
  type: "progress";
  step: string;
  status: ProgressStatus;
};

export type ResultEvent = {
  type: "result";
  data: unknown;
};

export type SqlEvent = {
  type: "sql";
  data: string;
};

export type ExplanationEvent = {
  type: "explanation";
  data: string;
};

export type ChartEvent = {
  type: "chart";
  data: ChartSpec | null;
};

export type ErrorEvent = {
  type: "error";
  message: string;
};

export type ChartType = "bar" | "line" | "pie" | "kpi" | "table";

export type ChartSpec = {
  type: ChartType;
  x_axis?: string;
  y_axis?: string;
  title?: string;
};

export type AgentEvent =
  | ProgressEvent
  | ResultEvent
  | SqlEvent
  | ExplanationEvent
  | ChartEvent
  | ErrorEvent;

export type StepState = {
  step: string;
  status: ProgressStatus;
  updatedAt: number;
};

export type HistoryTurn = {
  role: "user" | "assistant";
  content: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  status?: "streaming" | "done" | "error";
  steps?: StepState[];
  result?: unknown;
  sql?: string;
  explanation?: string;
  chart?: ChartSpec | null;
  error?: string;
};
