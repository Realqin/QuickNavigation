import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useDict } from '../hooks/useDict';
import type { PageType } from '../types/tabs';

const PROJECT_KEY = 'quicknav-project';
const ENV_KEY = 'quicknav-environment';

export interface TabWorkspaceState {
  customized: boolean;
  project: number | null;
  environment: number | null;
}

interface WorkspaceContextValue {
  globalProject: number | null;
  globalEnvironment: number | null;
  globalVersion: number;
  projectOptions: Array<{ label: string; value: number }>;
  environmentOptions: Array<{ label: string; value: number }>;
  projectIdMap: Record<number, string>;
  environmentIdMap: Record<number, string>;
  setGlobalProject: (project: number) => void;
  setGlobalEnvironment: (environment: number) => void;
  getTabState: (tabKey: PageType) => TabWorkspaceState;
  setTabFilter: (tabKey: PageType, patch: Partial<TabWorkspaceState>) => void;
  resetTabFilter: (tabKey: PageType) => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function loadStorageNumber(key: string): number | null {
  const raw = localStorage.getItem(key);
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function resolveOption(
  value: number | null,
  options: Array<{ label: string; value: number }>,
): number | null {
  if (value != null && options.some((item) => item.value === value)) {
    return value;
  }
  return options[0]?.value ?? null;
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { options: projectOptions, idMap: projectIdMap, items: projectItems } = useDict('project');
  const { options: environmentOptions, idMap: environmentIdMap, items: envItems } = useDict('environment');

  const [globalProject, setGlobalProjectState] = useState<number | null>(() =>
    loadStorageNumber(PROJECT_KEY),
  );
  const [globalEnvironment, setGlobalEnvironmentState] = useState<number | null>(() =>
    loadStorageNumber(ENV_KEY),
  );
  const [globalVersion, setGlobalVersion] = useState(0);
  const tabStatesRef = useRef<Partial<Record<PageType, TabWorkspaceState>>>({});

  const resolvedProject = useMemo(
    () => resolveOption(globalProject, projectOptions),
    [globalProject, projectOptions],
  );
  const resolvedEnvironment = useMemo(
    () => resolveOption(globalEnvironment, environmentOptions),
    [globalEnvironment, environmentOptions],
  );

  useEffect(() => {
    if (projectItems.length && resolvedProject == null && projectOptions[0]) {
      setGlobalProjectState(projectOptions[0].value);
    }
  }, [projectItems.length, projectOptions, resolvedProject]);

  useEffect(() => {
    if (envItems.length && resolvedEnvironment == null && environmentOptions[0]) {
      setGlobalEnvironmentState(environmentOptions[0].value);
    }
  }, [envItems.length, environmentOptions, resolvedEnvironment]);

  useEffect(() => {
    if (resolvedProject != null) {
      localStorage.setItem(PROJECT_KEY, String(resolvedProject));
    }
    if (resolvedEnvironment != null) {
      localStorage.setItem(ENV_KEY, String(resolvedEnvironment));
    }
  }, [resolvedProject, resolvedEnvironment]);

  const bumpGlobal = useCallback(() => {
    setGlobalVersion((value) => value + 1);
  }, []);

  const syncTabsToGlobal = useCallback(
    (project: number | null, environment: number | null) => {
      const next: Partial<Record<PageType, TabWorkspaceState>> = { ...tabStatesRef.current };
      for (const [key, state] of Object.entries(next)) {
        if (!state?.customized) {
          next[key as PageType] = {
            customized: false,
            project,
            environment,
          };
        }
      }
      tabStatesRef.current = next;
    },
    [],
  );

  const setGlobalProject = useCallback(
    (project: number) => {
      setGlobalProjectState(project);
      syncTabsToGlobal(project, resolvedEnvironment);
      bumpGlobal();
    },
    [bumpGlobal, resolvedEnvironment, syncTabsToGlobal],
  );

  const setGlobalEnvironment = useCallback(
    (environment: number) => {
      setGlobalEnvironmentState(environment);
      syncTabsToGlobal(resolvedProject, environment);
      bumpGlobal();
    },
    [bumpGlobal, resolvedProject, syncTabsToGlobal],
  );

  const getTabState = useCallback(
    (tabKey: PageType): TabWorkspaceState => {
      const existing = tabStatesRef.current[tabKey];
      if (existing) {
        return existing;
      }
      return {
        customized: false,
        project: resolvedProject,
        environment: resolvedEnvironment,
      };
    },
    [resolvedEnvironment, resolvedProject],
  );

  const setTabFilter = useCallback((tabKey: PageType, patch: Partial<TabWorkspaceState>) => {
    const current = tabStatesRef.current[tabKey] ?? {
      customized: false,
      project: resolvedProject,
      environment: resolvedEnvironment,
    };
    tabStatesRef.current[tabKey] = {
      ...current,
      ...patch,
      customized: patch.customized ?? true,
    };
  }, [resolvedEnvironment, resolvedProject]);

  const resetTabFilter = useCallback(
    (tabKey: PageType) => {
      tabStatesRef.current[tabKey] = {
        customized: false,
        project: resolvedProject,
        environment: resolvedEnvironment,
      };
    },
    [resolvedEnvironment, resolvedProject],
  );

  const value = useMemo(
    () => ({
      globalProject: resolvedProject,
      globalEnvironment: resolvedEnvironment,
      globalVersion,
      projectOptions,
      environmentOptions,
      projectIdMap,
      environmentIdMap,
      setGlobalProject,
      setGlobalEnvironment,
      getTabState,
      setTabFilter,
      resetTabFilter,
    }),
    [
      resolvedProject,
      resolvedEnvironment,
      globalVersion,
      projectOptions,
      environmentOptions,
      projectIdMap,
      environmentIdMap,
      setGlobalProject,
      setGlobalEnvironment,
      getTabState,
      setTabFilter,
      resetTabFilter,
    ],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error('useWorkspace must be used within WorkspaceProvider');
  }
  return ctx;
}
