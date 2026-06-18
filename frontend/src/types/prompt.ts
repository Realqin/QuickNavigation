export const PROMPT_TYPE_OPTIONS = [
  '通用对话',
  '需求评审',
  '测试用例',
  '缺陷分析',
  '接口用例',
  'AI分析',
] as const;

export type PromptType = (typeof PROMPT_TYPE_OPTIONS)[number];

export interface PromptTemplate {
  id: string;
  prompt_type: string;
  name: string;
  description: string;
  content: string;
  base_content: string;
  response_type: string;
  response_format: string;
  remark: string;
  enabled: boolean;
  is_default: boolean;
  is_preset: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PromptTemplateFormValues {
  prompt_type: string;
  name: string;
  description: string;
  base_content: string;
  response_type: string;
  response_format: string;
  remark?: string;
  enabled: boolean;
  is_default: boolean;
  is_preset?: boolean;
}

export const RESPONSE_TYPE_PRESETS = [
  { value: '', label: '未指定', format: '' },
  {
    value: 'markdown',
    label: 'Markdown 正文',
    format: '使用 Markdown 正文输出，按标题和项目符号组织内容。',
  },
  {
    value: 'markdown-table',
    label: 'Markdown 表格',
    format: '使用 Markdown 表格输出，并补充必要说明。',
  },
  {
    value: 'json-object',
    label: 'JSON 对象',
    format: '{\n  "content": ""\n}',
  },
  {
    value: 'json-array',
    label: 'JSON 数组',
    format: '[\n  {\n    "name": "",\n    "value": ""\n  }\n]',
  },
  {
    value: 'plain-text',
    label: '纯文本',
    format: '使用纯文本输出，不要使用 Markdown 标记。',
  },
] as const;

export function getResponseTypeLabel(value?: string): string {
  return RESPONSE_TYPE_PRESETS.find((item) => item.value === value)?.label || value || '-';
}
