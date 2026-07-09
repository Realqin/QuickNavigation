import { closeEmbedSession, fetchEmbedSession } from '../api';
import { rewriteEmbedConsoleUrl } from './consoleProxy';
import { resolveOmnidbOpenUrl } from './omnidb';
import { resolveRedpandaOpenUrl } from './redpanda';
import { resolveRedisinsightOpenUrl } from './redisinsight';
import { resolveSshwiftyOpenUrl } from './sshwifty';

const pendingCloseTimers = new Map<string, number>();
const EMBED_SESSION_CLOSE_DELAY_MS = 800;

export interface EmbedSessionTarget {
  url: string;
  /** false 表示须顶级窗口打开（如 SSH / Web Crypto） */
  embed: boolean;
}

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

export async function loadEmbedSessionTarget(sessionId: string): Promise<EmbedSessionTarget> {
  const session = await fetchEmbedSession(sessionId);
  const embedUrl = session.embed_url?.trim();
  if (!embedUrl) {
    throw new Error('empty embed url');
  }
  if (session.console_type === 'terminal') {
    return { url: resolveSshwiftyOpenUrl(embedUrl), embed: false };
  }
  if (session.console_type === 'database') {
    return { url: resolveOmnidbOpenUrl(embedUrl), embed: true };
  }
  if (session.console_type === 'redis') {
    return { url: resolveRedisinsightOpenUrl(embedUrl), embed: true };
  }
  if (session.console_type === 'kafka') {
    return { url: resolveRedpandaOpenUrl(embedUrl), embed: true };
  }
  return { url: rewriteEmbedConsoleUrl(embedUrl), embed: true };
}

export async function loadEmbedSessionUrl(sessionId: string): Promise<string> {
  const target = await loadEmbedSessionTarget(sessionId);
  return target.url;
}
