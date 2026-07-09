import { useCallback, useEffect, useState } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import type { PageType } from '../types/tabs';

export function useTabWorkspaceFilter(tabKey: PageType) {
  const {
    globalProject,
    globalEnvironment,
    globalVersion,
    getTabState,
    setTabFilter,
    resetTabFilter,
  } = useWorkspace();

  const [project, setProjectState] = useState<number | null>(() => getTabState(tabKey).project);
  const [environment, setEnvironmentState] = useState<number | null>(
    () => getTabState(tabKey).environment,
  );
  const [customized, setCustomized] = useState(() => getTabState(tabKey).customized);

  useEffect(() => {
    const state = getTabState(tabKey);
    setProjectState(state.project);
    setEnvironmentState(state.environment);
    setCustomized(state.customized);
  }, [getTabState, tabKey, globalVersion]);

  const setProject = useCallback(
    (value: number | null | undefined) => {
      const next = value ?? null;
      setProjectState(next);
      setCustomized(true);
      setTabFilter(tabKey, { project: next, environment, customized: true });
    },
    [environment, setTabFilter, tabKey],
  );

  const setEnvironment = useCallback(
    (value: number | null | undefined) => {
      const next = value ?? null;
      setEnvironmentState(next);
      setCustomized(true);
      setTabFilter(tabKey, { project, environment: next, customized: true });
    },
    [project, setTabFilter, tabKey],
  );

  const setWorkspace = useCallback(
    (nextProject: number | null | undefined, nextEnvironment: number | null | undefined) => {
      const projectValue = nextProject ?? null;
      const environmentValue = nextEnvironment ?? null;
      setProjectState(projectValue);
      setEnvironmentState(environmentValue);
      setCustomized(true);
      setTabFilter(tabKey, {
        project: projectValue,
        environment: environmentValue,
        customized: true,
      });
    },
    [setTabFilter, tabKey],
  );

  const resetToGlobal = useCallback(() => {
    resetTabFilter(tabKey);
    setProjectState(globalProject);
    setEnvironmentState(globalEnvironment);
    setCustomized(false);
  }, [globalEnvironment, globalProject, resetTabFilter, tabKey]);

  return {
    project: project ?? globalProject,
    environment: environment ?? globalEnvironment,
    customized,
    globalVersion,
    setProject,
    setEnvironment,
    setWorkspace,
    resetToGlobal,
  };
}
