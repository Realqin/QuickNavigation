export interface MqttMessageRecord {
  id: string;
  topic: string;
  payload: string;
  receivedAt: string;
  receivedAtMs: number;
  colorIndex: number;
}

export interface MqttConnectionForm {
  host: string;
  port: number;
  wsPath: string;
  username: string;
  password: string;
  clientId: string;
}
