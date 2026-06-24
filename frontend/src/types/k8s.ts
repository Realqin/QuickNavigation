export type K8sProvider = 'native' | 'kubesphere' | 'kuboard';
export type K8sAuthType = 'password' | 'token';

export interface K8sClusterConfig {
  id: number;
  name: string;
  api_server: string;
  provider: K8sProvider;
  auth_type: K8sAuthType;
  username?: string | null;
  verify_ssl: boolean;
  password_set: boolean;
  sort_order: number;
  last_connected_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface K8sClusterFormValues {
  name: string;
  api_server: string;
  provider: K8sProvider;
  auth_type: K8sAuthType;
  username?: string;
  password?: string;
  verify_ssl: boolean;
}

export interface K8sConnectResult {
  ok: boolean;
  message: string;
  cluster_id: number;
  version: string;
  namespace_count: number;
  latency_ms?: number | null;
}

export interface K8sProject {
  name: string;
  status: string;
  created_at?: string | null;
}

export interface K8sContainer {
  name: string;
  image: string;
  ready: boolean;
  restart_count: number;
}

export interface K8sPod {
  name: string;
  namespace: string;
  status: string;
  phase: string;
  node: string;
  pod_ip: string;
  host_ip: string;
  containers: K8sContainer[];
  restart_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface K8sService {
  id: string;
  project: string;
  namespace: string;
  service_name: string;
  service_type: string;
  cluster_ip: string;
  ports: string[];
  external_ports: number[];
  workload_kind?: string | null;
  workload_name?: string | null;
  status: string;
  ready_replicas: number;
  replicas: number;
  nodes: string[];
  pod_ips: string[];
  updated_at?: string | null;
  pods: K8sPod[];
  scalable: boolean;
}

export interface K8sScalePayload {
  namespace: string;
  workload_kind: string;
  workload_name: string;
  delta: number;
}

export interface K8sScaleResult {
  namespace: string;
  workload_kind: string;
  workload_name: string;
  replicas: number;
  message: string;
}

export interface K8sPodLogResult {
  namespace: string;
  pod_name: string;
  container: string;
  logs: string;
}
