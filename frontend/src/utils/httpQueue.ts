/** 限制浏览器到同源 API 的并发连接数，避免 Windows 客户端端口耗尽 (ERR_ADDRESS_IN_USE)。 */
const MAX_CONCURRENT = 4;

let activeCount = 0;
const waitQueue: Array<() => void> = [];

export async function acquireHttpSlot(): Promise<void> {
  if (activeCount < MAX_CONCURRENT) {
    activeCount += 1;
    return;
  }
  await new Promise<void>((resolve) => {
    waitQueue.push(() => {
      activeCount += 1;
      resolve();
    });
  });
}

export function releaseHttpSlot(): void {
  activeCount = Math.max(0, activeCount - 1);
  const next = waitQueue.shift();
  if (next) {
    next();
  }
}
