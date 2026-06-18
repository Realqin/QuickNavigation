export interface AiAnalysisResult {
  analysis: string;
  model: string;
  prompt_type: string;
  prompt_name: string;
  scenario: string;
  truncated: boolean;
  meta: Record<string, unknown>;
}

export interface AiAnalysisRequest {
  logId?: number | null;
  scenario?: string;
  title?: string | null;
  summary?: string | null;
  context?: string | null;
  content?: string | null;
  contentLabel?: string;
  promptType?: string;
  extra?: Record<string, unknown>;
}
