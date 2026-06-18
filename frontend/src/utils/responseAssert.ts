export type ResponseAssertMode = 'text' | 'jsonpath';

export type AssertOperator =
  | 'eq'
  | 'ne'
  | 'lt'
  | 'lte'
  | 'gt'
  | 'gte'
  | 'contains'
  | 'not_contains'
  | 'starts_with'
  | 'not_starts_with'
  | 'ends_with'
  | 'not_ends_with'
  | 'is_null'
  | 'is_not_null'
  | 'is_empty'
  | 'is_not_empty'
  | 'between'
  | 'not_between'
  | 'in_list'
  | 'not_in_list';

export type AssertConnector = 'and' | 'or';

export interface ResponseAssertRule {
  id: string;
  path: string;
  operator: AssertOperator;
  expected?: string;
  expectedTo?: string;
  connector?: AssertConnector;
}

export const ASSERT_OPERATOR_OPTIONS: Array<{ value: AssertOperator; label: string; needsValue?: boolean }> = [
  { value: 'eq', label: '=' },
  { value: 'ne', label: '!=' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '<=' },
  { value: 'gt', label: '>' },
  { value: 'gte', label: '>=' },
  { value: 'contains', label: '包含' },
  { value: 'not_contains', label: '不包含' },
  { value: 'starts_with', label: '开头是' },
  { value: 'not_starts_with', label: '开头不是' },
  { value: 'ends_with', label: '结尾是' },
  { value: 'not_ends_with', label: '结尾不是' },
  { value: 'is_null', label: '是 null', needsValue: false },
  { value: 'is_not_null', label: '不是 null', needsValue: false },
  { value: 'is_empty', label: '是空的', needsValue: false },
  { value: 'is_not_empty', label: '是非空的', needsValue: false },
  { value: 'between', label: '介于' },
  { value: 'not_between', label: '不介于' },
  { value: 'in_list', label: '在列表' },
  { value: 'not_in_list', label: '不在列表' },
];

export const ASSERT_CONNECTOR_OPTIONS: Array<{ value: AssertConnector; label: string }> = [
  { value: 'and', label: '且' },
  { value: 'or', label: '或' },
];

export const RESPONSE_ASSERT_MODE_OPTIONS: Array<{ value: ResponseAssertMode; label: string }> = [
  { value: 'text', label: '文本校验' },
  { value: 'jsonpath', label: '关键值校验' },
];

export function operatorNeedsValue(operator: AssertOperator): boolean {
  return !ASSERT_OPERATOR_OPTIONS.find((item) => item.value === operator && item.needsValue === false);
}

export function operatorNeedsRange(operator: AssertOperator): boolean {
  return operator === 'between' || operator === 'not_between';
}

export function createEmptyRule(): ResponseAssertRule {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    path: '$.',
    operator: 'eq',
    expected: '',
    connector: 'and',
  };
}

export function parseAssertRules(raw?: string | null): ResponseAssertRule[] {
  if (!raw?.trim()) {
    return [createEmptyRule()];
  }
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [createEmptyRule()];
    }
    const rules = parsed
      .filter((item) => item && typeof item === 'object')
      .map((item, index) => ({
        id: String(item.id || `${index}-${item.path || 'rule'}`),
        path: String(item.path || '$'),
        operator: (item.operator || 'eq') as AssertOperator,
        expected: item.expected != null ? String(item.expected) : '',
        expectedTo: item.expectedTo != null ? String(item.expectedTo) : undefined,
        connector: (item.connector === 'or' ? 'or' : 'and') as AssertConnector,
      }));
    return rules.length ? rules : [createEmptyRule()];
  } catch {
    return [createEmptyRule()];
  }
}

export function serializeAssertRules(rules: ResponseAssertRule[]): string {
  const payload = rules
    .filter((rule) => rule.path.trim())
    .map(({ id, path, operator, expected, expectedTo, connector }) => ({
      id,
      path: path.trim(),
      operator,
      expected: expected?.trim() || undefined,
      expectedTo: expectedTo?.trim() || undefined,
      connector,
    }));
  return JSON.stringify(payload, null, 2);
}

export function formatExpectedResponseDisplay(
  mode: ResponseAssertMode | string | undefined,
  expectedResponse?: string | null,
  rulesRaw?: string | null,
): string {
  const assertMode = mode === 'jsonpath' ? 'jsonpath' : 'text';
  if (assertMode === 'jsonpath') {
    const rules = parseAssertRules(rulesRaw);
    if (!rules.length || !rules.some((rule) => rule.path.trim())) {
      return '关键值校验（未配置）';
    }
    return rules
      .map((rule, index) => {
        const op = ASSERT_OPERATOR_OPTIONS.find((item) => item.value === rule.operator)?.label || rule.operator;
        const value = operatorNeedsValue(rule.operator)
          ? operatorNeedsRange(rule.operator)
            ? `${rule.expected ?? ''}~${rule.expectedTo ?? ''}`
            : (rule.expected ?? '')
          : '';
        const line = `${rule.path} ${op}${value ? ` ${value}` : ''}`;
        if (index === 0) {
          return line;
        }
        const conn = rules[index - 1].connector === 'or' ? ' 或 ' : ' 且 ';
        return `${conn}${line}`;
      })
      .join('');
  }
  return expectedResponse?.trim() || '-';
}

function isEmptyValue(value: unknown): boolean {
  if (value == null) {
    return true;
  }
  if (typeof value === 'string') {
    return value.trim() === '';
  }
  if (Array.isArray(value)) {
    return value.length === 0;
  }
  if (typeof value === 'object') {
    return Object.keys(value as object).length === 0;
  }
  return false;
}

function toComparableString(value: unknown): string {
  if (value == null) {
    return '';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}

function parseListValues(raw?: string): string[] {
  if (!raw?.trim()) {
    return [];
  }
  const text = raw.trim();
  if (text.startsWith('[')) {
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        return parsed.map((item) => String(item));
      }
    } catch {
      // fall through
    }
  }
  return text.split(/[,，;；\n]/).map((item) => item.trim()).filter(Boolean);
}

function parseNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  const text = String(value ?? '').trim();
  if (!text) {
    return null;
  }
  const num = Number(text);
  return Number.isFinite(num) ? num : null;
}

function tokenizeJsonPath(path: string): string[] {
  const normalized = path.trim().replace(/^\$\.?/, '');
  if (!normalized) {
    return [];
  }
  const tokens: string[] = [];
  const pattern = /([^[.\]]+)|\[(\d+)\]|(?:\['([^']+)'\])|(?:\["([^"]+)"\])/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(normalized))) {
    if (match[1]) {
      tokens.push(match[1]);
    } else if (match[2] != null) {
      tokens.push(String(match[2]));
    } else if (match[3] != null) {
      tokens.push(match[3]);
    } else if (match[4] != null) {
      tokens.push(match[4]);
    }
  }
  return tokens;
}

export function extractJsonPath(data: unknown, path: string): unknown {
  const trimmed = (path || '').trim();
  if (!trimmed || trimmed === '$') {
    return data;
  }
  const tokens = tokenizeJsonPath(trimmed);
  let current: unknown = data;
  for (const token of tokens) {
    if (current == null) {
      return undefined;
    }
    if (Array.isArray(current)) {
      const index = Number(token);
      current = Number.isInteger(index) ? current[index] : undefined;
      continue;
    }
    if (typeof current === 'object') {
      current = (current as Record<string, unknown>)[token];
      continue;
    }
    return undefined;
  }
  return current;
}

function evaluateRule(actualValue: unknown, rule: ResponseAssertRule): { pass: boolean; message: string } {
  const operatorLabel =
    ASSERT_OPERATOR_OPTIONS.find((item) => item.value === rule.operator)?.label || rule.operator;
  const actualText = toComparableString(actualValue);
  const expected = rule.expected ?? '';
  const expectedTo = rule.expectedTo ?? '';

  switch (rule.operator) {
    case 'is_null':
      return {
        pass: actualValue === null || actualValue === undefined,
        message: `${rule.path} 应为 null，实际 ${actualText || 'undefined'}`,
      };
    case 'is_not_null':
      return {
        pass: actualValue !== null && actualValue !== undefined,
        message: `${rule.path} 应非 null，实际 ${actualText || 'undefined'}`,
      };
    case 'is_empty':
      return {
        pass: isEmptyValue(actualValue),
        message: `${rule.path} 应为空，实际 ${actualText || 'undefined'}`,
      };
    case 'is_not_empty':
      return {
        pass: !isEmptyValue(actualValue),
        message: `${rule.path} 应非空，实际 ${actualText || 'undefined'}`,
      };
    case 'eq':
      return {
        pass: actualText === expected,
        message: `${rule.path} ${operatorLabel} ${expected}，实际 ${actualText}`,
      };
    case 'ne':
      return {
        pass: actualText !== expected,
        message: `${rule.path} ${operatorLabel} ${expected}，实际 ${actualText}`,
      };
    case 'contains':
      return {
        pass: actualText.includes(expected),
        message: `${rule.path} ${operatorLabel} ${expected}，实际 ${actualText}`,
      };
    case 'not_contains':
      return {
        pass: !actualText.includes(expected),
        message: `${rule.path} ${operatorLabel} ${expected}，实际 ${actualText}`,
      };
    case 'starts_with':
      return {
        pass: actualText.startsWith(expected),
        message: `${rule.path} ${operatorLabel} ${expected}，实际 ${actualText}`,
      };
    case 'not_starts_with':
      return {
        pass: !actualText.startsWith(expected),
        message: `${rule.path} ${operatorLabel} ${expected}，实际 ${actualText}`,
      };
    case 'ends_with':
      return {
        pass: actualText.endsWith(expected),
        message: `${rule.path} ${operatorLabel} ${expected}，实际 ${actualText}`,
      };
    case 'not_ends_with':
      return {
        pass: !actualText.endsWith(expected),
        message: `${rule.path} ${operatorLabel} ${expected}，实际 ${actualText}`,
      };
    case 'lt':
    case 'lte':
    case 'gt':
    case 'gte': {
      const actualNum = parseNumber(actualValue);
      const expectedNum = parseNumber(expected);
      if (actualNum == null || expectedNum == null) {
        return {
          pass: false,
          message: `${rule.path} 无法比较数值：实际 ${actualText}，预期 ${expected}`,
        };
      }
      const pass =
        rule.operator === 'lt'
          ? actualNum < expectedNum
          : rule.operator === 'lte'
            ? actualNum <= expectedNum
            : rule.operator === 'gt'
              ? actualNum > expectedNum
              : actualNum >= expectedNum;
      return {
        pass,
        message: `${rule.path} ${operatorLabel} ${expected}，实际 ${actualNum}`,
      };
    }
    case 'between':
    case 'not_between': {
      const actualNum = parseNumber(actualValue);
      const min = parseNumber(expected);
      const max = parseNumber(expectedTo);
      if (actualNum == null || min == null || max == null) {
        return {
          pass: false,
          message: `${rule.path} 无法比较区间：实际 ${actualText}，预期 ${expected}~${expectedTo}`,
        };
      }
      const lower = Math.min(min, max);
      const upper = Math.max(min, max);
      const inRange = actualNum >= lower && actualNum <= upper;
      return {
        pass: rule.operator === 'between' ? inRange : !inRange,
        message: `${rule.path} ${operatorLabel} ${expected}~${expectedTo}，实际 ${actualNum}`,
      };
    }
    case 'in_list':
    case 'not_in_list': {
      const list = parseListValues(expected);
      const pass = list.includes(actualText);
      return {
        pass: rule.operator === 'in_list' ? pass : !pass,
        message: `${rule.path} ${operatorLabel} [${list.join(', ')}]，实际 ${actualText}`,
      };
    }
    default:
      return { pass: false, message: `${rule.path} 未知运算符 ${rule.operator}` };
  }
}

function normalizeJsonText(text: string): string | null {
  try {
    return JSON.stringify(JSON.parse(text));
  } catch {
    return null;
  }
}

export function evaluateTextAssert(actualBody: string, expectedBody?: string | null): { pass: boolean; message: string } {
  const actual = actualBody ?? '';
  const expected = expectedBody ?? '';
  if (!expected.trim()) {
    return { pass: true, message: '未配置文本预期，跳过响应体校验' };
  }

  const actualJson = normalizeJsonText(actual);
  const expectedJson = normalizeJsonText(expected);
  if (actualJson != null && expectedJson != null) {
    const pass = actualJson === expectedJson;
    return {
      pass,
      message: pass ? '响应 JSON 与预期完全一致' : '响应 JSON 与预期不一致',
    };
  }

  const pass = actual.trim() === expected.trim();
  return {
    pass,
    message: pass ? '响应文本与预期完全一致' : '响应文本与预期不一致',
  };
}

export function evaluateJsonPathAssert(
  actualBody: string,
  rulesRaw?: string | null,
): { pass: boolean; message: string; failures: string[] } {
  const rules = parseAssertRules(rulesRaw).filter((rule) => rule.path.trim());
  if (!rules.length) {
    return { pass: true, message: '未配置关键值规则，跳过响应体校验', failures: [] };
  }

  let parsedBody: unknown = actualBody;
  try {
    parsedBody = JSON.parse(actualBody);
  } catch {
    return {
      pass: false,
      message: '响应体不是有效 JSON，无法进行关键值校验',
      failures: ['响应体不是有效 JSON'],
    };
  }

  const failures: string[] = [];
  let combined = evaluateRule(extractJsonPath(parsedBody, rules[0].path), rules[0]);
  if (!combined.pass) {
    failures.push(combined.message);
  }
  let result = combined.pass;

  for (let index = 1; index < rules.length; index += 1) {
    const rule = rules[index];
    const connector = rules[index - 1].connector === 'or' ? 'or' : 'and';
    const current = evaluateRule(extractJsonPath(parsedBody, rule.path), rule);
    if (!current.pass) {
      failures.push(current.message);
    }
    result = connector === 'or' ? result || current.pass : result && current.pass;
  }

  return {
    pass: result,
    message: result ? '关键值校验通过' : failures[0] || '关键值校验未通过',
    failures,
  };
}

export function evaluateResponseAssert(input: {
  mode?: ResponseAssertMode | string | null;
  expectedResponse?: string | null;
  rulesRaw?: string | null;
  actualBody: string;
}): { pass: boolean; message: string; failures: string[] } {
  const mode = input.mode === 'jsonpath' ? 'jsonpath' : 'text';
  if (mode === 'jsonpath') {
    return evaluateJsonPathAssert(input.actualBody, input.rulesRaw);
  }
  const textResult = evaluateTextAssert(input.actualBody, input.expectedResponse);
  return { ...textResult, failures: textResult.pass ? [] : [textResult.message] };
}
