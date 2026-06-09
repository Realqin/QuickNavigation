import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchDictItems } from '../api';
import type { DictItem, DictType } from '../types';

export function dictToOptions(items: DictItem[]) {
  return items.map((item) => ({
    label: item.description ? `${item.name}（${item.description}）` : item.name,
    value: item.id,
  }));
}

export function useDict(type?: DictType) {
  const [items, setItems] = useState<DictItem[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await fetchDictItems(type);
      setItems(list);
    } finally {
      setLoading(false);
    }
  }, [type]);

  useEffect(() => {
    load();
  }, [load]);

  const options = useMemo(() => dictToOptions(items), [items]);
  const idMap = useMemo(
    () => Object.fromEntries(items.map((item) => [item.id, item.name])),
    [items],
  );

  return { items, options, idMap, loading, reload: load };
}

export function useDictGroup() {
  const projects = useDict('project');
  const environments = useDict('environment');
  const labels = useDict('label');

  const reloadAll = useCallback(async () => {
    await Promise.all([projects.reload(), environments.reload(), labels.reload()]);
  }, [projects, environments, labels]);

  return { projects, environments, labels, reloadAll };
}
