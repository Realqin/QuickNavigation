const BEIJING = 'Asia/Shanghai';

function parseBackendDate(value: string): Date {
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  return new Date(normalized.replace(/([+-]\d{2})(\d{2})$/, '$1:$2'));
}

export function formatBeijingTime(value?: string | null): string | null {
  if (!value) {
    return null;
  }
  const date = parseBackendDate(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: BEIJING,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
}

export function formatDateTime(value?: string | null): string | null {
  return formatBeijingTime(value);
}
