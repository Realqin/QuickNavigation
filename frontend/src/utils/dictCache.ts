import type { DictItem, DictType } from '../types';

type CacheKey = string;

function toKey(type?: DictType): CacheKey {
  return type ?? '__all__';
}

const cache = new Map<CacheKey, DictItem[]>();
const inflight = new Map<CacheKey, Promise<DictItem[]>>();
const listeners = new Map<CacheKey, Set<() => void>>();

function notifyKey(key: CacheKey): void {
  listeners.get(key)?.forEach((cb) => cb());
}

export function getCachedDictItems(type?: DictType): DictItem[] | undefined {
  return cache.get(toKey(type));
}

export function setCachedDictItems(type: DictType | undefined, items: DictItem[]): void {
  cache.set(toKey(type), items);
  notifyKey(toKey(type));
}

export function invalidateDictCache(type?: DictType): void {
  if (type === undefined) {
    cache.clear();
    listeners.forEach((_, key) => notifyKey(key));
    return;
  }
  cache.delete(toKey(type));
  notifyKey(toKey(type));
}

export function subscribeDictCache(type: DictType | undefined, cb: () => void): () => void {
  const key = toKey(type);
  let set = listeners.get(key);
  if (!set) {
    set = new Set();
    listeners.set(key, set);
  }
  set.add(cb);
  return () => {
    set!.delete(cb);
    if (set!.size === 0) {
      listeners.delete(key);
    }
  };
}

export function getInflightDictRequest(type?: DictType): Promise<DictItem[]> | undefined {
  return inflight.get(toKey(type));
}

export function trackInflightDictRequest(
  type: DictType | undefined,
  promise: Promise<DictItem[]>,
): void {
  const key = toKey(type);
  inflight.set(key, promise);
  void promise.finally(() => {
    if (inflight.get(key) === promise) {
      inflight.delete(key);
    }
  });
}
