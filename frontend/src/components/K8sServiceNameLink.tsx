import { Typography } from 'antd';
import { useMemo } from 'react';
import type { K8sClusterConfig } from '../types/k8s';
import { resolveK8sServiceOpenUrlFromPayload } from '../utils/k8sServiceUrl';

interface Props {
  cluster: K8sClusterConfig | null;
  namespace: string;
  serviceName: string;
  payload?: Record<string, unknown> | null;
  strong?: boolean;
  className?: string;
}

export default function K8sServiceNameLink({
  cluster,
  namespace,
  serviceName,
  payload,
  strong = false,
  className,
}: Props) {
  const url = useMemo(
    () => resolveK8sServiceOpenUrlFromPayload(cluster, namespace, serviceName, payload),
    [cluster, namespace, payload, serviceName],
  );

  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className={`k8s-service-name-link${className ? ` ${className}` : ''}`}
        title="在控制台中打开"
        onClick={(event) => event.stopPropagation()}
      >
        <Typography.Text strong={strong}>{serviceName}</Typography.Text>
      </a>
    );
  }

  return (
    <Typography.Text strong={strong} className={className}>
      {serviceName}
    </Typography.Text>
  );
}
