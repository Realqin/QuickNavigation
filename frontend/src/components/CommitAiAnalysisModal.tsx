import { Alert, Button, Modal, Spin, Typography } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchAiAnalysis } from '../api';
import type { AiAnalysisResult } from '../types/aiAnalysis';
import {
  LOG_AI_MODAL_VARIANTS,
  resolveLogAiModalTitle,
  type LogAiModalVariant,
} from '../utils/logAiModal';
import { streamAiAnalysis } from '../utils/streamAiAnalysis';
import { stripAnalysisPreamble } from '../utils/stripAnalysisPreamble';
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
  const [streaming, setStreaming] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [reasoningText, setReasoningText] = useState('');
  const [contentPreview, setContentPreview] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AiAnalysisResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const streamPanelRef = useRef<HTMLDivElement | null>(null);

  const config = LOG_AI_MODAL_VARIANTS[variant];
  const title = resolveLogAiModalTitle(variant, commitSha);
  const useStream = variant === 'analysis';

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

  const streamPanelText = streaming
    ? reasoningText || contentPreview
    : reasoningText;
  const streamPanelTitle = reasoningText ? '思考过程' : '生成中';
  const showReasoningAfterResult = Boolean(reasoningText) && !streaming && Boolean(result);

  const resetState = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
    setStreaming(false);
    setStatusMessage('');
    setReasoningText('');
    setContentPreview('');
    setError(null);
    setResult(null);
  }, []);

  const loadAnalysis = useCallback(async () => {
    if (logId == null) {
      setError(`缺少日志信息，无法${config.title}`);
      setResult(null);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setStreaming(useStream);
    setError(null);
    setResult(null);
    setStatusMessage(useStream ? config.loadingText : '');
    setReasoningText('');
    setContentPreview('');

    const payload = {
      log_id: logId,
      scenario: config.scenario,
      prompt_type: config.promptType,
      summary: summary ?? undefined,
    };

    try {
      if (useStream) {
        await streamAiAnalysis(
          payload,
          {
            onStatus: (message) => {
              setStatusMessage(message);
            },
            onReasoning: (delta) => {
              setReasoningText((prev) => prev + delta);
            },
            onContent: (delta) => {
              setContentPreview((prev) => prev + delta);
            },
            onDone: (data) => {
              setResult({
                ...data,
                analysis: stripAnalysisPreamble(data.analysis),
              });
              setStreaming(false);
              setStatusMessage('');
              setContentPreview('');
            },
            onError: (detail) => {
              setError(detail);
              setStreaming(false);
            },
          },
          controller.signal,
        );
      } else {
        const data = await fetchAiAnalysis(payload);
        setResult({
          ...data,
          analysis: stripAnalysisPreamble(data.analysis),
        });
      }
    } catch (err) {
      if (controller.signal.aborted) {
        return;
      }
      setResult(null);
      setError(resolveErrorMessage(err, config.errorFallback));
      setStreaming(false);
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
        setStreaming(false);
      }
    }
  }, [config.errorFallback, config.loadingText, config.promptType, config.scenario, config.title, logId, summary, useStream]);

  useEffect(() => {
    if (!open) {
      resetState();
      return;
    }
    void loadAnalysis();
  }, [open, loadAnalysis, resetState]);

  useEffect(() => {
    if (!streaming || !streamPanelRef.current) {
      return;
    }
    streamPanelRef.current.scrollTop = streamPanelRef.current.scrollHeight;
  }, [reasoningText, contentPreview, streaming]);

  const showStreamPanel = streaming && Boolean(reasoningText);
  const showResult = Boolean(result) && !streaming;

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

      {loading && !useStream ? (
        <div className="commit-ai-analysis-modal__loading">
          <Spin tip={config.loadingText} />
        </div>
      ) : null}

      {useStream && (streaming || statusMessage) && !error ? (
        <div className="commit-ai-analysis-modal__stream-status">
          <Spin size="small" />
          <Typography.Text type="secondary">{statusMessage || config.loadingText}</Typography.Text>
        </div>
      ) : null}

      {useStream && showStreamPanel ? (
        <div className="commit-ai-analysis-modal__stream">
          <Typography.Text strong className="commit-ai-analysis-modal__stream-title">
            {streamPanelTitle}
          </Typography.Text>
          <div ref={streamPanelRef} className="commit-ai-analysis-modal__stream-body">
            {streamPanelText || '等待模型响应…'}
          </div>
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

      {showResult && result ? (
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
            <>
              <Typography.Text strong className="commit-ai-analysis-modal__result-title">
                分析结果
              </Typography.Text>
              <MarkdownContent
                content={stripAnalysisPreamble(result.analysis)}
                className="commit-ai-analysis-modal__body markdown-body"
              />
              {showReasoningAfterResult ? (
                <details className="commit-ai-analysis-modal__stream-collapse commit-ai-analysis-modal__stream-collapse--after">
                  <summary>思考过程</summary>
                  <div className="commit-ai-analysis-modal__stream-body commit-ai-analysis-modal__stream-body--done">
                    {reasoningText}
                  </div>
                </details>
              ) : null}
            </>
          )}
        </>
      ) : null}

      <div className="commit-ai-analysis-modal__footer">
        {error ? (
          <Button onClick={() => void loadAnalysis()} loading={loading || streaming}>
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
