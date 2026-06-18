import { Alert, Button, Modal, Spin, Typography } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchAiAnalysis } from '../api';
import type { AiAnalysisResult } from '../types/aiAnalysis';
import {
  LOG_AI_MODAL_VARIANTS,
  resolveLogAiModalTitle,
  type LogAiModalVariant,
} from '../utils/logAiModal';
import CodeInterpretationView from './CodeInterpretationView';
import MarkdownContent from './MarkdownContent';
import './CommitAiAnalysisModal.css';

interface Props {
  logId: number | null;
  commitSha?: string | null;
  summary?: string | null;
  variant?: LogAiModalVariant;
  open: boolean;
  onClose: () => void;
}

function resolveErrorMessage(error: unknown, fallback: string): string {
  const detail =
    (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
    (error instanceof Error ? error.message : null);
  return detail ? String(detail) : fallback;
}

export default function CommitAiAnalysisModal({
  logId,
  commitSha,
  summary,
  variant = 'analysis',
  open,
  onClose,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AiAnalysisResult | null>(null);

  const config = LOG_AI_MODAL_VARIANTS[variant];
  const title = resolveLogAiModalTitle(variant, commitSha);

  const metaText = useMemo(() => {
    if (!result) {
      return null;
    }
    const parts = [
      result.prompt_name ? `提示词：${result.prompt_name}` : null,
      result.model ? `模型：${result.model}` : null,
      result.truncated ? '变更内容已截断' : null,
    ].filter(Boolean);
    return parts.length ? parts.join(' · ') : null;
  }, [result]);

  const loadAnalysis = useCallback(async () => {
    if (logId == null) {
      setError(`缺少日志信息，无法${config.title}`);
      setResult(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await fetchAiAnalysis({
        log_id: logId,
        scenario: config.scenario,
        prompt_type: config.promptType,
        summary: summary ?? undefined,
      });
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(resolveErrorMessage(err, config.errorFallback));
    } finally {
      setLoading(false);
    }
  }, [config.errorFallback, config.promptType, config.scenario, config.title, logId, summary]);

  useEffect(() => {
    if (!open) {
      setLoading(false);
      setError(null);
      setResult(null);
      return;
    }
    void loadAnalysis();
  }, [open, loadAnalysis]);

  return (
    <Modal
      className={['commit-ai-analysis-modal', config.modalClassName].filter(Boolean).join(' ')}
      title={title}
      open={open}
      onCancel={onClose}
      footer={null}
      width={config.modalWidth}
      destroyOnHidden
    >
      {summary ? (
        <Typography.Paragraph type="secondary" className="commit-ai-analysis-modal__summary">
          摘要：{summary}
        </Typography.Paragraph>
      ) : null}

      {loading ? (
        <div className="commit-ai-analysis-modal__loading">
          <Spin tip={config.loadingText} />
        </div>
      ) : null}

      {!loading && error ? (
        <Alert
          type="error"
          showIcon
          message={config.failureTitle}
          description={error}
          style={{ marginBottom: 12 }}
        />
      ) : null}

      {!loading && result ? (
        <>
          {metaText ? (
            <Typography.Paragraph type="secondary" className="commit-ai-analysis-modal__meta">
              {metaText}
            </Typography.Paragraph>
          ) : null}
          {variant === 'code-interpretation' && result.interpretation?.files?.length ? (
            <div className="commit-ai-analysis-modal__body commit-ai-analysis-modal__body--interpretation">
              <CodeInterpretationView data={result.interpretation} />
            </div>
          ) : (
            <MarkdownContent
              content={result.analysis}
              className="commit-ai-analysis-modal__body markdown-body"
            />
          )}
        </>
      ) : null}

      <div className="commit-ai-analysis-modal__footer">
        {error ? (
          <Button onClick={() => void loadAnalysis()} loading={loading}>
            {config.retryLabel}
          </Button>
        ) : null}
        <Button type="primary" onClick={onClose}>
          关闭
        </Button>
      </div>
    </Modal>
  );
}
