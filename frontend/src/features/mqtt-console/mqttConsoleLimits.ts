/** Maximum retained message count. Older records are dropped first. */
export const MQTT_MESSAGE_MAX_COUNT = 10000;

/** Batch UI updates to reduce render pressure during high-frequency streams. */
export const MQTT_MESSAGE_FLUSH_MS = 100;

/** Flush sooner if a burst grows past this size. */
export const MQTT_MESSAGE_PENDING_MAX = 500;

/** Maximum single connection lifetime in milliseconds. */
export const MQTT_CONNECTION_MAX_MS = 30 * 60 * 1000;
