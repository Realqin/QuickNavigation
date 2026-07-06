interface ParsedMessagePayload {
  payload: string;
  code?: string;
}

function normalizeCode(value: unknown): string | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed ? trimmed : undefined;
  }
  return undefined;
}

function findMessageCode(value: unknown, depth = 0): string | undefined {
  if (depth > 2 || !value || typeof value !== 'object') {
    return undefined;
  }

  if (Array.isArray(value)) {
    for (const item of value.slice(0, 5)) {
      const code = findMessageCode(item, depth + 1);
      if (code) {
        return code;
      }
    }
    return undefined;
  }

  const record = value as Record<string, unknown>;
  const directCode = normalizeCode(record.code);
  if (directCode) {
    return directCode;
  }

  return findMessageCode(record.data, depth + 1);
}

export function parseMessagePayload(raw: string): ParsedMessagePayload {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { payload: raw };
  }

  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      return {
        payload: JSON.stringify(parsed),
        code: findMessageCode(parsed),
      };
    } catch {
      return { payload: raw };
    }
  }

  return { payload: raw };
}
