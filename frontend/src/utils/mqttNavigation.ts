import { openMqttConsoleSession } from '../api';

export function buildMqttConsoleUrl(connectionId?: number, sessionId?: string): string {
  const params = new URLSearchParams();
  if (connectionId != null) {
    params.set('connectionId', String(connectionId));
  }
  if (sessionId) {
    params.set('sessionId', sessionId);
  }
  const query = params.toString();
  return query ? `/mqtt?${query}` : '/mqtt';
}

export async function openMqttConsole(connectionId: number): Promise<void> {
  const data = await openMqttConsoleSession(connectionId);
  const url = buildMqttConsoleUrl(connectionId, data.session_id ?? undefined);
  const opened = window.open(url, '_blank', 'noopener,noreferrer');
  if (!opened) {
    throw new Error('browser blocked popup');
  }
}
