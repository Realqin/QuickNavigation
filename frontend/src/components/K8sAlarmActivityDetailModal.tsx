import { Modal } from 'antd';
import K8sAlarmDetailContent, { type K8sAlarmDetailData } from './K8sAlarmDetailContent';
import { useK8sClusterById } from '../hooks/useK8sClusterById';
import type { ActivityLog } from '../types';
import { extractK8sAlarmClusterId, isK8sAlarmActivityLog } from '../utils/k8sAlarmActivityLog';

interface Props {
  log: ActivityLog | null;
  open: boolean;
  onClose: () => void;
}

function toDetailData(log: ActivityLog): K8sAlarmDetailData | null {
  if (!isK8sAlarmActivityLog(log)) {
    return null;
  }
  const payload = log.payload ?? {};
  const alertType =
    payload.alert_type === 'restart'
      ? 'restart'
      : payload.alert_type === 'exception'
        ? 'exception'
        : 'watermark';
  const status = payload.status === 'firing' ? 'firing' : 'resolved';
  return {
    title: log.title,
    alert_type: alertType,
    status,
    namespace: String(payload.namespace ?? ''),
    service_name: String(payload.service_name ?? ''),
    occurred_at: log.occurred_at,
    summary: log.summary,
    payload,
  };
}

export default function K8sAlarmActivityDetailModal({ log, open, onClose }: Props) {
  const clusterId = log ? extractK8sAlarmClusterId(log) : null;
  const cluster = useK8sClusterById(clusterId);
  const detailData = log ? toDetailData(log) : null;
  return (
    <Modal
      title={detailData?.title ?? '告警详情'}
      open={open}
      onCancel={onClose}
      footer={null}
      width={720}
      destroyOnHidden
    >
      {detailData ? <K8sAlarmDetailContent data={detailData} cluster={cluster} /> : null}
    </Modal>
  );
}
