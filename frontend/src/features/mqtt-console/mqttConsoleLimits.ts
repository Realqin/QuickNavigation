/** 消息流最多保留条数（超出后剔除最旧消息） */
export const MQTT_MESSAGE_MAX_COUNT = 1000;

/** 批量刷新的最大间隔（毫秒），降低高频消息时的渲染压力 */
export const MQTT_MESSAGE_FLUSH_MS = 100;

/** 待刷新缓冲超过该条数时立即落盘，避免积压 */
export const MQTT_MESSAGE_PENDING_MAX = 200;

/** 单次连接最长维持时间（毫秒） */
export const MQTT_CONNECTION_MAX_MS = 30 * 60 * 1000;
