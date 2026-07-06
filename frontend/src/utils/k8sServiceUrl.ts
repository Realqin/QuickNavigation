import type { K8sClusterConfig, K8sService } from '../types/k8s';

const KUBESPHERE_WORKLOAD_PATH: Record<string, string> = {
  Deployment: 'deployments',
  StatefulSet: 'statefulsets',
  DaemonSet: 'daemonsets',
};

export interface K8sServiceLinkContext {
  namespace: string;
  service_name: string;
  workload_kind?: string | null;
  workload_name?: string | null;
  external_ports?: number[];
  port?: number | null;
}

export function buildExternalServiceUrl(cluster: K8sClusterConfig | null, port?: number | null) {
  if (!cluster || port == null || port <= 0) {
    return '';
  }
  try {
    const apiUrl = new URL(cluster.api_server);
    return `${apiUrl.protocol}//${apiUrl.hostname}:${port}/#/overview`;
  } catch {
    return '';
  }
}

export function buildKubesphereWorkloadUrl(
  cluster: K8sClusterConfig | null,
  ctx: Pick<K8sServiceLinkContext, 'namespace' | 'workload_kind' | 'workload_name'>,
) {
  if (!cluster || cluster.provider !== 'kubesphere') {
    return '';
  }
  const resource = ctx.workload_kind ? KUBESPHERE_WORKLOAD_PATH[ctx.workload_kind] : '';
  if (!resource || !ctx.workload_name || !ctx.namespace) {
    return '';
  }
  try {
    const base = new URL(cluster.api_server);
    return `${base.origin}/clusters/default/projects/${encodeURIComponent(ctx.namespace)}/${resource}/${encodeURIComponent(ctx.workload_name)}`;
  } catch {
    return '';
  }
}

export function buildKubesphereDeploymentUrlByServiceName(
  cluster: K8sClusterConfig | null,
  ctx: Pick<K8sServiceLinkContext, 'namespace' | 'service_name'>,
) {
  if (!cluster || cluster.provider !== 'kubesphere' || !ctx.namespace || !ctx.service_name) {
    return '';
  }
  try {
    const base = new URL(cluster.api_server);
    return `${base.origin}/clusters/default/projects/${encodeURIComponent(ctx.namespace)}/deployments/${encodeURIComponent(ctx.service_name)}`;
  } catch {
    return '';
  }
}

export function resolveK8sServiceOpenUrl(
  cluster: K8sClusterConfig | null,
  ctx: K8sServiceLinkContext,
): string {
  const kubesphereUrl = buildKubesphereWorkloadUrl(cluster, ctx);
  if (kubesphereUrl) {
    return kubesphereUrl;
  }
  if (cluster?.provider === 'kubesphere') {
    const deploymentUrl = buildKubesphereDeploymentUrlByServiceName(cluster, ctx);
    if (deploymentUrl) {
      return deploymentUrl;
    }
  }
  const port = ctx.port ?? ctx.external_ports?.[0];
  return buildExternalServiceUrl(cluster, port);
}

export function resolveK8sServiceOpenUrlFromService(
  cluster: K8sClusterConfig | null,
  service: K8sService,
): string {
  return resolveK8sServiceOpenUrl(cluster, {
    namespace: service.namespace,
    service_name: service.service_name,
    workload_kind: service.workload_kind,
    workload_name: service.workload_name,
    external_ports: service.external_ports,
  });
}

export function resolveK8sServiceOpenUrlFromPayload(
  cluster: K8sClusterConfig | null,
  namespace: string,
  serviceName: string,
  payload?: Record<string, unknown> | null,
): string {
  const portValue = payload?.port;
  const port =
    typeof portValue === 'number'
      ? portValue
      : typeof portValue === 'string' && portValue.trim()
        ? Number(portValue)
        : null;
  const externalPorts = Array.isArray(payload?.external_ports)
    ? payload.external_ports.filter((item): item is number => typeof item === 'number')
    : undefined;
  return resolveK8sServiceOpenUrl(cluster, {
    namespace,
    service_name: serviceName,
    workload_kind:
      typeof payload?.workload_kind === 'string' ? payload.workload_kind : null,
    workload_name:
      typeof payload?.workload_name === 'string' ? payload.workload_name : null,
    external_ports: externalPorts,
    port: Number.isFinite(port) ? port : null,
  });
}
