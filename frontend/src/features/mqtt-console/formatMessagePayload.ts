/** JSON 压缩为单行；非 JSON 原样返回 */
export function formatMessagePayload(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) {
    return raw;
  }
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      return JSON.stringify(JSON.parse(trimmed));
    } catch {
      return raw;
    }
  }
  return raw;
}
