import type { ActivityLog } from '../types';

export function isApiMonitorChangeLog(log: ActivityLog): boolean {
  return log.source_type === 'api-monitor' && log.payload?.event === 'api_change';
}

export function buildApiMonitorServiceId(log: ActivityLog): string | null {
  if (!log.connection_id) {
    return null;
  }
  const linkKey = typeof log.payload?.link_key === 'string' ? log.payload.link_key : 'main';
  return `${log.connection_id}:${linkKey}`;
}

export function getApiMonitorChangeCount(log: ActivityLog): number {
  if (!isApiMonitorChangeLog(log)) {
    return 0;
  }
  const added = Number(log.payload?.added_count || 0);
  const modified = Number(log.payload?.modified_count || 0);
  const removed = Number(log.payload?.removed_count || 0);
  return added + modified + removed;
}
