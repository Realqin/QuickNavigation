import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchDictItems } from '../api';
import { useAuth } from '../contexts/AuthContext';
import type { DictItem, DictType } from '../types';
import { getCachedDictItems, subscribeDictCache } from '../utils/dictCache';

export {
  buildLabelColorMap,
  buildLabelIconIndexMap,
  buildLabelOrderMap,
  sortConnectionsByTypeOrder,
} from '../utils/labelTheme';

export function dictToOptions(items: DictItem[]) {
  return items.map((item) => ({
    label: item.description ? `${item.name} (${item.description})` : item.name,
    value: item.id,
  }));
}

export function useDict(type?: DictType) {
  const { token, loading: authLoading } = useAuth();
  const canFetch = Boolean(token) && !authLoading;
  const [items, setItems] = useState<DictItem[]>(() => getCachedDictItems(type) ?? []);
  const [loading, setLoading] = useState(() => canFetch && getCachedDictItems(type) === undefined);

  const load = useCallback(async (force = false) => {
    if (!canFetch && !force) {
      return;
    }
    if (force || getCachedDictItems(type) === undefined) {
      setLoading(true);
    }
    try {
      const list = await fetchDictItems(type, { force });
      setItems(list);
    } catch {
      if (getCachedDictItems(type) === undefined) {
        setItems([]);
      }
    } finally {
      setLoading(false);
    }
  }, [canFetch, type]);

  useEffect(() => {
    if (!canFetch) {
      return;
    }
    void load();
    return subscribeDictCache(type, () => {
      const cached = getCachedDictItems(type);
      if (cached) {
        setItems(cached);
      }
    });
  }, [canFetch, load, type]);

  const options = useMemo(() => dictToOptions(items), [items]);
  const idMap = useMemo(
    () => Object.fromEntries(items.map((item) => [item.id, item.name])),
    [items],
  );

  const reload = useCallback(() => load(true), [load]);

  return { items, options, idMap, loading, reload };
}

export function useDictGroup() {
  const projects = useDict('project');
  const environments = useDict('environment');
  const labels = useDict('label');
  const connectionGroups = useDict('connection_group');

  const reloadAll = useCallback(async () => {
    await Promise.all([
      projects.reload(),
      environments.reload(),
      labels.reload(),
      connectionGroups.reload(),
    ]);
  }, [projects, environments, labels, connectionGroups]);

  return { projects, environments, labels, connectionGroups, reloadAll };
}
