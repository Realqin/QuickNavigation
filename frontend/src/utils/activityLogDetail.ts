import type { ActivityLog } from '../types';
import { isApiMonitorChangeLog } from './apiMonitorChangeLog';
import { isK8sAlarmActivityLog } from './k8sAlarmActivityLog';
import { isSchemaChangeLog } from './schemaChangeLog';

export function extractCommitSha(log: ActivityLog): string | null {
  const sha = log.payload?.commit_sha;
  return typeof sha === 'string' && sha ? sha : null;
}

export function canOpenActivityLogDetail(log: ActivityLog): boolean {
  return (
    isSchemaChangeLog(log) ||
    isApiMonitorChangeLog(log) ||
    isK8sAlarmActivityLog(log) ||
    Boolean(extractCommitSha(log))
  );
}

export function resolveActivityLogDetail(
  log: ActivityLog,
): 'schema' | 'api-monitor' | 'k8s-alarm' | 'diff' | null {
  if (isSchemaChangeLog(log)) {
    return 'schema';
  }
  if (isApiMonitorChangeLog(log)) {
    return 'api-monitor';
  }
  if (isK8sAlarmActivityLog(log)) {
    return 'k8s-alarm';
  }
  if (extractCommitSha(log)) {
    return 'diff';
  }
  return null;
}
