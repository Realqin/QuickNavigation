import type { AiAnalysisResult } from '../types/aiAnalysis';
import { resolveApiBaseUrl } from './apiBase';

export type AiAnalysisStreamEvent =
  | { type: 'status'; message: string }
  | { type: 'reasoning'; delta: string; text?: string }
  | { type: 'content'; delta: string; text?: string }
  | { type: 'done'; result: AiAnalysisResult }
  | { type: 'error'; detail: string };

export interface AiAnalysisStreamHandlers {
  onEvent?: (event: AiAnalysisStreamEvent) => void;
  onStatus?: (message: string) => void;
  onReasoning?: (delta: string) => void;
  onContent?: (delta: string) => void;
  onDone?: (result: AiAnalysisResult) => void;
  onError?: (detail: string) => void;
}

function resolveStreamUrl(): string {
  const base = resolveApiBaseUrl().replace(/\/$/, '');
  return `${base}/api/ai-analysis/stream`;
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string };
    if (typeof data.detail === 'string' && data.detail.trim()) {
      return data.detail;
    }
  } catch {
    // ignore
  }
  return `请求失败（HTTP ${response.status}）`;
}

function dispatchEvent(event: AiAnalysisStreamEvent, handlers: AiAnalysisStreamHandlers) {
  handlers.onEvent?.(event);
  if (event.type === 'status') {
    handlers.onStatus?.(event.message);
    return;
  }
  if (event.type === 'reasoning') {
    handlers.onReasoning?.(event.delta);
    return;
  }
  if (event.type === 'content') {
    handlers.onContent?.(event.delta);
    return;
  }
  if (event.type === 'done') {
    handlers.onDone?.(event.result);
    return;
  }
  if (event.type === 'error') {
    handlers.onError?.(event.detail);
  }
}

export async function streamAiAnalysis(
  payload: {
    log_id?: number;
    scenario?: string;
    title?: string;
    summary?: string;
    context?: string;
    content?: string;
    content_label?: string;
    prompt_type?: string;
    extra?: Record<string, unknown>;
  },
  handlers: AiAnalysisStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(resolveStreamUrl(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    const errorEvent: AiAnalysisStreamEvent = { type: 'error', detail };
    dispatchEvent(errorEvent, handlers);
    throw new Error(detail);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    const detail = '浏览器不支持流式响应';
    dispatchEvent({ type: 'error', detail }, handlers);
    throw new Error(detail);
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() ?? '';

    for (const chunk of chunks) {
      const line = chunk
        .split('\n')
        .map((item) => item.trim())
        .find((item) => item.startsWith('data:'));
      if (!line) {
        continue;
      }
      const jsonText = line.slice(5).trim();
      if (!jsonText) {
        continue;
      }
      try {
        const event = JSON.parse(jsonText) as AiAnalysisStreamEvent;
        dispatchEvent(event, handlers);
        if (event.type === 'error') {
          throw new Error(event.detail);
        }
      } catch (error) {
        if (error instanceof Error && error.message !== jsonText) {
          throw error;
        }
      }
    }
  }
}
