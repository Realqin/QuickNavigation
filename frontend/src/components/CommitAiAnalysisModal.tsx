import { Alert, Button, Modal, Spin, Typography } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchAiAnalysis } from '../api';
import type { AiAnalysisResult } from '../types/aiAnalysis';
import MarkdownContent from './MarkdownContent';
import './CommitAiAnalysisModal.css';

interface Props {
  logId: number | null;
  commitSha?: string | null;
  summary?: string | null;
  open: boolean;
  onClose: () => void;
}

function resolveErrorMessage(error: unknown): string {
  const detail =
    (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
    (error instanceof Error ? error.message : null);
  return detail ? String(detail) : 'AI 分析失败，请稍后重试';
}

export default function CommitAiAnalysisModal({
  logId,
  commitSha,
  summary,
  open,
  onClose,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AiAnalysisResult | null>(null);

  const title = commitSha ? `AI 分析 · ${commitSha.slice(0, 7)}` : 'AI 分析';

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
      setError('缺少日志信息，无法分析');
      setResult(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await fetchAiAnalysis({
        log_id: logId,
        scenario: 'commit-diff',
        summary: summary ?? undefined,
      });
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(resolveErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [logId, summary]);

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
      className="commit-ai-analysis-modal"
      title={title}
      open={open}
      onCancel={onClose}
      footer={null}
      width={720}
      destroyOnHidden
    >
      {summary ? (
        <Typography.Paragraph type="secondary" className="commit-ai-analysis-modal__summary">
          摘要：{summary}
        </Typography.Paragraph>
      ) : null}

      {loading ? (
        <div className="commit-ai-analysis-modal__loading">
          <Spin tip="AI 分析中，请稍候…" />
        </div>
      ) : null}

      {!loading && error ? (
        <Alert
          type="error"
          showIcon
          message="分析失败"
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
          <MarkdownContent
            content={result.analysis}
            className="commit-ai-analysis-modal__body markdown-body"
          />
        </>
      ) : null}

      <div className="commit-ai-analysis-modal__footer">
        {error ? (
          <Button onClick={() => void loadAnalysis()} loading={loading}>
            重新分析
          </Button>
        ) : null}
        <Button type="primary" onClick={onClose}>
          关闭
        </Button>
      </div>
    </Modal>
  );
}
