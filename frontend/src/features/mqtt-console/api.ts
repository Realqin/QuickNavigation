import type { MqttConsoleConfig } from '../../types';
import { fetchMqttConsoleConfig } from '../../api';

export async function fetchMqttConfig(connectionId: number): Promise<MqttConsoleConfig> {
  return fetchMqttConsoleConfig(connectionId);
}
