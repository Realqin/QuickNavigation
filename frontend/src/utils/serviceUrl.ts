export function resolveServiceBaseUrl(baseUrl: string | undefined, defaultPort: number): string {
  if (!baseUrl?.trim()) {
    return `${window.location.protocol}//${window.location.hostname}:${defaultPort}`;
  }
  const target = new URL(baseUrl);
  target.protocol = window.location.protocol;
  target.hostname = window.location.hostname;
  target.port = String(defaultPort);
  return target.toString();
}
