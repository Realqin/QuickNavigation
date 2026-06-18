import { Modal, Typography } from 'antd';

interface Props {
  logId: number | null;
  commitSha?: string | null;
  summary?: string | null;
  open: boolean;
  onClose: () => void;
}

export default function CommitAiAnalysisModal({
  logId,
  commitSha,
  summary,
  open,
  onClose,
}: Props) {
  const title = commitSha ? `AI 分析 · ${commitSha.slice(0, 7)}` : 'AI 分析';

  return (
    <Modal title={title} open={open} onCancel={onClose} footer={null} width={720} destroyOnHidden>
      {summary ? (
        <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
          摘要：{summary}
        </Typography.Paragraph>
      ) : null}
      <Typography.Text type="secondary">
        AI 分析功能开发中，后续将在此展示对本次提交修改内容的智能解读。
        {logId != null ? `（日志 ID：${logId}）` : ''}
      </Typography.Text>
    </Modal>
  );
}
