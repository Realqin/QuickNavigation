export function buildK8sExecWebSocketUrl(params: {
  clusterId: number;
  namespace: string;
  podName: string;
  container?: string;
}): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const search = new URLSearchParams({
    namespace: params.namespace,
    pod_name: params.podName,
  });
  if (params.container) {
    search.set('container', params.container);
  }
  return `${protocol}//${window.location.host}/ws/k8s/clusters/${params.clusterId}/exec?${search.toString()}`;
}
