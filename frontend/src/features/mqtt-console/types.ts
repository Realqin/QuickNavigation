export interface MqttMessageRecord {
  id: string;
  topic: string;
  payload: string;
  code?: string;
  receivedAt: string;
  receivedAtMs: number;
  backgroundColor: string;
}

export interface MqttConnectionForm {
  host: string;
  port: number;
  wsPath: string;
  username: string;
  password: string;
  clientId: string;
}
