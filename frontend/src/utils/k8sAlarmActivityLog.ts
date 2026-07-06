import type { ActivityLog } from '../types';

export function isK8sAlarmActivityLog(log: ActivityLog): boolean {
  return log.source_type === 'k8s' && log.payload?.event === 'k8s_alarm';
}

export function getK8sAlarmAlertTypeLabel(log: ActivityLog): string {
  const alertType = log.payload?.alert_type;
  if (alertType === 'restart') return '重启';
  if (alertType === 'exception') return '异常';
  if (alertType === 'watermark') return 'Watermark';
  return '告警';
}

export function extractK8sAlarmClusterId(log: ActivityLog): number | null {
  if (!isK8sAlarmActivityLog(log)) {
    return null;
  }
  const clusterId = log.payload?.cluster_id;
  return typeof clusterId === 'number' ? clusterId : null;
}
