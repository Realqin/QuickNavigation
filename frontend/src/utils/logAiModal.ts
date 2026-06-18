export type LogAiModalVariant = 'analysis' | 'code-interpretation';

export interface LogAiModalVariantConfig {
  title: string;
  scenario: string;
  promptType: string;
  loadingText: string;
  errorFallback: string;
  retryLabel: string;
  failureTitle: string;
  modalWidth: number;
  modalClassName?: string;
}

export const LOG_AI_MODAL_VARIANTS: Record<LogAiModalVariant, LogAiModalVariantConfig> = {
  analysis: {
    title: 'AI 分析',
    scenario: 'commit-diff',
    promptType: 'AI分析',
    loadingText: 'AI 分析中，请稍候…',
    errorFallback: 'AI 分析失败，请稍后重试',
    retryLabel: '重新分析',
    failureTitle: '分析失败',
    modalWidth: 720,
  },
  'code-interpretation': {
    title: '代码解读',
    scenario: 'code-interpretation',
    promptType: '代码解读',
    loadingText: '正在逐行解读代码，请稍候…',
    errorFallback: '代码解读失败，请稍后重试',
    retryLabel: '重新解读',
    failureTitle: '解读失败',
    modalWidth: 1080,
    modalClassName: 'commit-ai-analysis-modal--code-interpretation',
  },
};

export function resolveLogAiModalTitle(variant: LogAiModalVariant, commitSha?: string | null): string {
  const base = LOG_AI_MODAL_VARIANTS[variant].title;
  if (commitSha) {
    return `${base} · ${commitSha.slice(0, 7)}`;
  }
  return base;
}
