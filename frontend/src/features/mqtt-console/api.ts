import axios from 'axios';
import type { MqttConsoleConfig } from '../../types';

const client = axios.create({
  baseURL: '/',
  timeout: 15000,
});

export async function fetchMqttConfig(connectionId: number): Promise<MqttConsoleConfig> {
  const { data } = await client.get<MqttConsoleConfig>(
    `/api/connections/${connectionId}/mqtt-config`,
  );
  return data;
}
