export interface LlmConfig {
  id: string;
  name: string;
  api_url: string;
  api_key?: string;
  has_api_key: boolean;
  model_name: string;
  context_limit: number;
  vision_enabled: boolean;
  stream_enabled: boolean;
  enabled: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface LlmConfigFormValues {
  name: string;
  api_url: string;
  api_key: string;
  model_name: string;
  context_limit: number;
  vision_enabled: boolean;
  stream_enabled: boolean;
  enabled: boolean;
}

export interface LlmConnectionTestPayload {
  api_url: string;
  api_key?: string;
  model_name: string;
  config_id?: string | null;
}

export interface LlmModelsPayload {
  api_url: string;
  api_key?: string;
  config_id?: string | null;
}
