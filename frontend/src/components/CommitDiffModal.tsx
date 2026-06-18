import { Button, Modal, Space, Spin, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { fetchLogDiff } from '../api';
import type { ActivityLogDiff } from '../types';
import type { LogAiModalVariant } from '../utils/logAiModal';
import { fileDiffTitle, parseUnifiedDiff, type DiffCellType } from '../utils/parseUnifiedDiff';
import CommitAiAnalysisModal from './CommitAiAnalysisModal';
import './CommitDiffModal.css';

interface Props {
  logId: number | null;
  commitSha?: string | null;
  summary?: string | null;
  open: boolean;
  onClose: () => void;
}

function emptyDiffHint(provider?: string | null): string {
  if (provider === 'gitlab') {
    return '暂无 diff 内容。请在「仓库访问配置」中填写 GitLab Token 与 Base URL，或于 backend/.env 配置后重启后端。';
  }
  return '暂无 diff 内容。请在「仓库访问配置」中填写 GitHub Token，或于 backend/.env 配置后重启后端。';
}

function cellClass(type: DiffCellType): string {
  return `commit-diff-cell commit-diff-cell--${type}`;
}

export default function CommitDiffModal({
  logId,
  commitSha,
  summary,
  open,
  onClose,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [diffData, setDiffData] = useState<ActivityLogDiff | null>(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiVariant, setAiVariant] = useState<LogAiModalVariant>('analysis');

  useEffect(() => {
    if (!open || logId == null) {
      setDiffData(null);
      return;
    }
    setLoading(true);
    fetchLogDiff(logId)
      .then(setDiffData)
      .catch(() => setDiffData(null))
      .finally(() => setLoading(false));
  }, [open, logId]);

  const fileDiffs = useMemo(
    () => parseUnifiedDiff(diffData?.diff ?? ''),
    [diffData?.diff],
  );

  useEffect(() => {
    if (!open) {
      setAiOpen(false);
      setAiVariant('analysis');
    }
  }, [open]);

  const openAiModal = (variant: LogAiModalVariant) => {
    setAiVariant(variant);
    setAiOpen(true);
  };

  const title = commitSha ? `提交对比 · ${commitSha.slice(0, 7)}` : '提交对比';
  const hasDiff = fileDiffs.length > 0;

  return (
    <Modal
      className="commit-diff-modal"
      title={title}
      open={open}
      onCancel={onClose}
      footer={null}
      width={1100}
      destroyOnHidden
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Spin />
        </div>
      ) : (
        <>
          {diffData?.repo && (
            <Typography.Paragraph type="secondary" className="commit-diff-meta">
              仓库：{diffData.repo}
              {diffData.branch ? ` · 分支：${diffData.branch}` : ''}
            </Typography.Paragraph>
          )}

          {hasDiff ? (
            <div className="commit-diff-scroll">
              {fileDiffs.map((file) => (
                <div className="commit-diff-file" key={fileDiffTitle(file)}>
                  {file.isBinary ? (
                    <>
                      <div className="commit-diff-file-header">
                        <div className="commit-diff-file-path">{fileDiffTitle(file)}</div>
                      </div>
                      <div className="commit-diff-binary">二进制文件已变更</div>
                    </>
                  ) : (
                    <>
                      <div className="commit-diff-file-header">
                        <div className="commit-diff-file-path">{fileDiffTitle(file)}</div>
                        <div className="commit-diff-columns">
                          <div className="commit-diff-column-title">修改前</div>
                          <div className="commit-diff-column-title">修改后</div>
                        </div>
                      </div>
                      {file.rows.map((row, index) => (
                        <div className="commit-diff-row" key={index}>
                          <div className={cellClass(row.leftType)}>
                            {row.left || '\u00a0'}
                          </div>
                          <div className={cellClass(row.rightType)}>
                            {row.right || '\u00a0'}
                          </div>
                        </div>
                      ))}
                    </>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="commit-diff-empty">
              {emptyDiffHint(diffData?.provider)}
            </div>
          )}

          {!loading && logId != null && commitSha ? (
            <div className="commit-diff-footer">
              <Space>
                <Button onClick={() => openAiModal('code-interpretation')}>代码解读</Button>
                <Button type="primary" onClick={() => openAiModal('analysis')}>
                  AI 分析
                </Button>
              </Space>
            </div>
          ) : null}
        </>
      )}

      <CommitAiAnalysisModal
        logId={logId}
        commitSha={commitSha}
        summary={summary}
        variant={aiVariant}
        open={aiOpen}
        onClose={() => setAiOpen(false)}
      />
    </Modal>
  );
}
