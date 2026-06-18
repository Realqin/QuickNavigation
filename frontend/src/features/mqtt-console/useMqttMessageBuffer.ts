import { useCallback, useEffect, useRef, useState } from 'react';
import {
  MQTT_MESSAGE_FLUSH_MS,
  MQTT_MESSAGE_MAX_COUNT,
  MQTT_MESSAGE_PENDING_MAX,
} from './mqttConsoleLimits';
import type { MqttMessageRecord } from './types';

function trimMessages(items: MqttMessageRecord[]): MqttMessageRecord[] {
  if (items.length <= MQTT_MESSAGE_MAX_COUNT) {
    return items;
  }
  return items.slice(0, MQTT_MESSAGE_MAX_COUNT);
}

export function useMqttMessageBuffer() {
  const [messages, setMessages] = useState<MqttMessageRecord[]>([]);
  const pendingRef = useRef<MqttMessageRecord[]>([]);
  const flushTimerRef = useRef<number | null>(null);
  const lastFlushAtRef = useRef(0);

  const flushPending = useCallback(() => {
    if (pendingRef.current.length === 0) {
      return;
    }
    const batch = pendingRef.current;
    pendingRef.current = [];
    lastFlushAtRef.current = Date.now();
    setMessages((prev) => trimMessages(batch.concat(prev)));
  }, []);

  const scheduleFlush = useCallback(() => {
    const elapsed = Date.now() - lastFlushAtRef.current;
    if (elapsed >= MQTT_MESSAGE_FLUSH_MS) {
      if (flushTimerRef.current != null) {
        window.clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      flushPending();
      return;
    }

    if (flushTimerRef.current != null) {
      return;
    }

    flushTimerRef.current = window.setTimeout(() => {
      flushTimerRef.current = null;
      flushPending();
    }, MQTT_MESSAGE_FLUSH_MS - elapsed);
  }, [flushPending]);

  const pushMessage = useCallback(
    (record: MqttMessageRecord) => {
      pendingRef.current.unshift(record);
      if (pendingRef.current.length >= MQTT_MESSAGE_PENDING_MAX) {
        flushPending();
        return;
      }
      scheduleFlush();
    },
    [flushPending, scheduleFlush],
  );

  const clearMessages = useCallback(() => {
    pendingRef.current = [];
    if (flushTimerRef.current != null) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    lastFlushAtRef.current = Date.now();
    setMessages([]);
  }, []);

  useEffect(
    () => () => {
      if (flushTimerRef.current != null) {
        window.clearTimeout(flushTimerRef.current);
      }
    },
    [],
  );

  return { messages, pushMessage, clearMessages };
}
