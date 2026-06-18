import { useEffect, useState, type RefObject } from 'react';

export function useContainerWidth(ref: RefObject<HTMLElement | null>) {
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const element = ref.current;
    if (!element) {
      return undefined;
    }

    const update = () => {
      setWidth(element.clientWidth);
    };

    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);

  return width;
}

/** 按权重分配列宽，末位为固定操作列宽度 */
export function distributeColumnWidths(
  containerWidth: number,
  weights: number[],
  fixedActionWidth: number,
): number[] {
  if (containerWidth <= 0 || weights.length === 0) {
    return [];
  }

  const flexibleWidth = Math.max(0, containerWidth - fixedActionWidth);
  const totalWeight = weights.reduce((sum, weight) => sum + weight, 0);
  if (totalWeight <= 0) {
    return weights.map(() => Math.floor(flexibleWidth / weights.length));
  }

  return weights.map((weight) => Math.max(56, Math.floor((flexibleWidth * weight) / totalWeight)));
}
