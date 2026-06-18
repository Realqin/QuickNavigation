import { closeEmbedSession, fetchEmbedSession } from '../api';

const pendingCloseTimers = new Map<string, number>();
const EMBED_SESSION_CLOSE_DELAY_MS = 800;

export function buildEmbedSessionPageUrl(sessionId: string): string {
  return `/embed/session/${encodeURIComponent(sessionId)}`;
}

export function cancelEmbedSessionClose(sessionId: string): void {
  const timer = pendingCloseTimers.get(sessionId);
  if (timer == null) {
    return;
  }
  window.clearTimeout(timer);
  pendingCloseTimers.delete(sessionId);
}

export function scheduleEmbedSessionClose(
  sessionId: string,
  delayMs = EMBED_SESSION_CLOSE_DELAY_MS,
): void {
  if (!sessionId) {
    return;
  }
  cancelEmbedSessionClose(sessionId);
  const timer = window.setTimeout(() => {
    pendingCloseTimers.delete(sessionId);
    closeEmbedSession(sessionId).catch(() => undefined);
  }, delayMs);
  pendingCloseTimers.set(sessionId, timer);
}

export function registerEmbedSessionCleanup(sessionId: string): () => void {
  if (!sessionId) {
    return () => undefined;
  }

  let closed = false;
  const cleanup = () => {
    if (closed) {
      return;
    }
    closed = true;
    cancelEmbedSessionClose(sessionId);
    closeEmbedSession(sessionId).catch(() => undefined);
  };

  const handleUnload = () => {
    cleanup();
  };

  window.addEventListener('pagehide', handleUnload);
  window.addEventListener('beforeunload', handleUnload);

  return () => {
    window.removeEventListener('pagehide', handleUnload);
    window.removeEventListener('beforeunload', handleUnload);
  };
}

export async function loadEmbedSessionUrl(sessionId: string): Promise<string> {
  const session = await fetchEmbedSession(sessionId);
  const embedUrl = session.embed_url?.trim();
  if (!embedUrl) {
    throw new Error('empty embed url');
  }
  return embedUrl;
}
