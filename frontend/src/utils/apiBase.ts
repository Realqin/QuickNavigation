/** 开发环境直连后端 8000，生产环境走同源 Nginx 反代 */
export function resolveApiBaseUrl(): string {
  if (import.meta.env.DEV) {
    return `http://${window.location.hostname}:8000`;
  }
  return '/';
}
