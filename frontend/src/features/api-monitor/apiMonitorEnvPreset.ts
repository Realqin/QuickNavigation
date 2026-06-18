export interface ApiMonitorEnvPreset {
  serverAddress: string;
  authorization: string;
}

export const API_MONITOR_ENV_PRESET_STORAGE_KEY = 'api-monitor-env-preset';

export const DEFAULT_API_MONITOR_ENV_PRESET: ApiMonitorEnvPreset = {
  serverAddress: 'http://10.100.0.184:11080',
  authorization: '',
};

export function readApiMonitorEnvPreset(): ApiMonitorEnvPreset {
  try {
    const raw = localStorage.getItem(API_MONITOR_ENV_PRESET_STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_API_MONITOR_ENV_PRESET };
    }
    const parsed = JSON.parse(raw) as Partial<ApiMonitorEnvPreset>;
    return {
      serverAddress: parsed.serverAddress?.trim() || DEFAULT_API_MONITOR_ENV_PRESET.serverAddress,
      authorization: parsed.authorization?.trim() || '',
    };
  } catch {
    return { ...DEFAULT_API_MONITOR_ENV_PRESET };
  }
}

export function writeApiMonitorEnvPreset(preset: ApiMonitorEnvPreset): void {
  localStorage.setItem(
    API_MONITOR_ENV_PRESET_STORAGE_KEY,
    JSON.stringify({
      serverAddress: preset.serverAddress.trim(),
      authorization: preset.authorization.trim(),
    }),
  );
}

export function normalizeAuthorization(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return '';
  }
  return trimmed.startsWith('Bearer ') ? trimmed : `Bearer ${trimmed}`;
}

export function buildDebugHeadersFromPreset(preset: ApiMonitorEnvPreset): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const authorization = normalizeAuthorization(preset.authorization);
  if (authorization) {
    headers.Authorization = authorization;
  }
  return headers;
}

export function formatDebugHeadersText(preset: ApiMonitorEnvPreset): string {
  return JSON.stringify(buildDebugHeadersFromPreset(preset), null, 2);
}
