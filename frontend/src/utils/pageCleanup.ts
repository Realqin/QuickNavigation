export type PageCleanupHandler = (reason: 'unmount' | 'unload') => void;

/**
 * 在组件卸载或浏览器关闭/刷新时执行清理（仅执行一次）。
 * unload 场景优先用于 sendBeacon 等必须在页面销毁前完成的操作。
 */
export function registerPageCleanup(onCleanup: PageCleanupHandler): () => void {
  let cleaned = false;

  const run = (reason: 'unmount' | 'unload') => {
    if (cleaned) {
      return;
    }
    cleaned = true;
    onCleanup(reason);
  };

  const handleUnload = () => run('unload');

  window.addEventListener('pagehide', handleUnload);
  window.addEventListener('beforeunload', handleUnload);

  return () => {
    window.removeEventListener('pagehide', handleUnload);
    window.removeEventListener('beforeunload', handleUnload);
    run('unmount');
  };
}
