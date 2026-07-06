import { useEffect, useState } from 'react';
import { fetchK8sClusters } from '../api';
import type { K8sClusterConfig } from '../types/k8s';

let clusterCache: K8sClusterConfig[] | null = null;
let clusterCachePromise: Promise<K8sClusterConfig[]> | null = null;

function loadClusters(): Promise<K8sClusterConfig[]> {
  if (clusterCache) {
    return Promise.resolve(clusterCache);
  }
  if (!clusterCachePromise) {
    clusterCachePromise = fetchK8sClusters()
      .then((list) => {
        clusterCache = list;
        return list;
      })
      .catch(() => {
        clusterCachePromise = null;
        return [];
      });
  }
  return clusterCachePromise;
}

export function useK8sClusterById(clusterId: number | null | undefined) {
  const [cluster, setCluster] = useState<K8sClusterConfig | null>(null);

  useEffect(() => {
    if (!clusterId) {
      setCluster(null);
      return;
    }
    let cancelled = false;
    loadClusters()
      .then((list) => {
        if (!cancelled) {
          setCluster(list.find((item) => item.id === clusterId) ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCluster(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [clusterId]);

  return cluster;
}
