import type { K8sConnectResult, K8sProject } from '../types/k8s';

export interface K8sConnectionSessionState {
  connectedId: number | null;
  connectInfo: K8sConnectResult | null;
  selectedId: number | null;
  selectedProject?: string;
  projects: K8sProject[];
}

const EMPTY: K8sConnectionSessionState = {
  connectedId: null,
  connectInfo: null,
  selectedId: null,
  selectedProject: undefined,
  projects: [],
};

let session: K8sConnectionSessionState = { ...EMPTY };

export function getK8sConnectionSession(): K8sConnectionSessionState {
  return session;
}

export function updateK8sConnectionSession(partial: Partial<K8sConnectionSessionState>): void {
  session = { ...session, ...partial };
}

export function clearK8sConnectionSession(): void {
  session = { ...EMPTY };
}

export function readK8sConnectionSessionSnapshot(): K8sConnectionSessionState {
  return { ...session };
}
