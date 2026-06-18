const BROKER_PART_RE = /^([^:\s]+)(?::(\d+))?$/;
const DEFAULT_KAFKA_PORT = 9092;

export function parseKafkaBrokers(
  host?: string | null,
  port?: number | null,
): string[] {
  const text = (host ?? '').trim();
  if (!text) return [];

  if (!text.includes(',') && !text.includes(':') && port) {
    return [`${text.trim()}:${port}`];
  }

  const brokers: string[] = [];
  for (const raw of text.split(/[,;\n]+/)) {
    const part = raw.trim();
    if (!part) continue;
    const matched = part.match(BROKER_PART_RE);
    if (!matched) continue;
    const brokerHost = matched[1].trim();
    const brokerPort = matched[2] ? Number(matched[2]) : (port ?? DEFAULT_KAFKA_PORT);
    brokers.push(`${brokerHost}:${brokerPort}`);
  }
  return brokers;
}

export function formatKafkaBrokersForInput(host?: string | null, port?: number | null): string {
  return parseKafkaBrokers(host, port).join(',');
}

export function normalizeKafkaBrokersInput(value: string): string {
  return parseKafkaBrokers(value).join(',');
}
