import { Empty } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import MqttMessageListItem from './MqttMessageListItem';
import type { MqttMessageRecord } from './types';

interface Props {
  messages: MqttMessageRecord[];
  selectedTopic?: string | null;
}

interface MeasuredRowProps {
  item: MqttMessageRecord;
  top: number;
  onResize: (id: string, height: number) => void;
}

const DEFAULT_ITEM_HEIGHT = 64;
const OVERSCAN_COUNT = 12;

function findStartIndex(
  messages: MqttMessageRecord[],
  offsets: number[],
  heights: Map<string, number>,
  scrollTop: number,
): number {
  let low = 0;
  let high = messages.length - 1;
  let result = messages.length;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const height = heights.get(messages[mid].id) ?? DEFAULT_ITEM_HEIGHT;
    if (offsets[mid] + height >= scrollTop) {
      result = mid;
      high = mid - 1;
    } else {
      low = mid + 1;
    }
  }

  return Math.max(0, Math.min(result, messages.length - 1));
}

function MeasuredMessageRow({ item, top, onResize }: MeasuredRowProps) {
  const rowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = rowRef.current;
    if (!node) return undefined;

    const measure = () => onResize(item.id, node.offsetHeight);
    measure();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure);
      return () => window.removeEventListener('resize', measure);
    }

    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [item.id, onResize]);

  return (
    <div
      ref={rowRef}
      className="mqtt-console__message-row"
      style={{ transform: `translateY(${top}px)` }}
    >
      <MqttMessageListItem item={item} />
    </div>
  );
}

export default function MqttMessageVirtualList({ messages, selectedTopic }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const itemHeightsRef = useRef(new Map<string, number>());
  const shouldStickToBottomRef = useRef(true);
  const animationFrameRef = useRef<number | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [panelHeight, setPanelHeight] = useState(0);
  const [heightVersion, setHeightVersion] = useState(0);

  const handleItemResize = useCallback((id: string, height: number) => {
    const nextHeight = Math.ceil(height);
    const prevHeight = itemHeightsRef.current.get(id);
    if (nextHeight > 0 && Math.abs((prevHeight ?? 0) - nextHeight) > 1) {
      itemHeightsRef.current.set(id, nextHeight);
      setHeightVersion((version) => version + 1);
    }
  }, []);

  useEffect(() => {
    const ids = new Set(messages.map((item) => item.id));
    let changed = false;
    for (const id of itemHeightsRef.current.keys()) {
      if (!ids.has(id)) {
        itemHeightsRef.current.delete(id);
        changed = true;
      }
    }
    if (changed) {
      setHeightVersion((version) => version + 1);
    }
  }, [messages]);

  const { offsets, totalHeight } = useMemo(() => {
    const nextOffsets: number[] = [];
    let nextTotalHeight = 0;
    for (const item of messages) {
      nextOffsets.push(nextTotalHeight);
      nextTotalHeight += itemHeightsRef.current.get(item.id) ?? DEFAULT_ITEM_HEIGHT;
    }
    return { offsets: nextOffsets, totalHeight: nextTotalHeight };
  }, [messages, heightVersion]);

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel || !shouldStickToBottomRef.current) return;
    const nextScrollTop = Math.max(0, totalHeight - panel.clientHeight);
    panel.scrollTop = nextScrollTop;
    setScrollTop(nextScrollTop);
  }, [messages, totalHeight]);

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return undefined;

    const updateHeight = () => setPanelHeight(panel.clientHeight);
    updateHeight();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateHeight);
      return () => window.removeEventListener('resize', updateHeight);
    }

    const observer = new ResizeObserver(updateHeight);
    observer.observe(panel);
    return () => observer.disconnect();
  }, []);

  useEffect(
    () => () => {
      if (animationFrameRef.current != null) {
        window.cancelAnimationFrame(animationFrameRef.current);
      }
    },
    [],
  );

  const handleScroll = () => {
    if (animationFrameRef.current != null) {
      return;
    }
    animationFrameRef.current = window.requestAnimationFrame(() => {
      animationFrameRef.current = null;
      const panel = panelRef.current;
      if (!panel) {
        return;
      }
      shouldStickToBottomRef.current =
        panel.scrollHeight - panel.scrollTop - panel.clientHeight < DEFAULT_ITEM_HEIGHT;
      setScrollTop(panel.scrollTop);
    });
  };

  const startIndex = Math.max(
    0,
    findStartIndex(messages, offsets, itemHeightsRef.current, scrollTop) - OVERSCAN_COUNT,
  );
  let endIndex = startIndex;
  const visibleBottom = scrollTop + panelHeight;
  while (
    endIndex < messages.length &&
    offsets[endIndex] < visibleBottom + DEFAULT_ITEM_HEIGHT * OVERSCAN_COUNT
  ) {
    endIndex += 1;
  }
  endIndex = Math.min(messages.length, endIndex + OVERSCAN_COUNT);

  const visibleMessages = useMemo(
    () => messages.slice(startIndex, endIndex),
    [messages, startIndex, endIndex],
  );

  if (messages.length === 0) {
    return (
      <div className="mqtt-console__message-panel">
        <Empty
          description={
            selectedTopic ? `暂无「${selectedTopic}」相关消息` : '暂无消息'
          }
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </div>
    );
  }

  return (
    <div className="mqtt-console__message-panel" ref={panelRef} onScroll={handleScroll}>
      <div
        className="mqtt-console__message-list mqtt-console__message-list--virtual"
        style={{ height: totalHeight }}
      >
        {visibleMessages.map((item, index) => (
          <MeasuredMessageRow
            key={item.id}
            item={item}
            top={offsets[startIndex + index] ?? 0}
            onResize={handleItemResize}
          />
        ))}
      </div>
    </div>
  );
}
