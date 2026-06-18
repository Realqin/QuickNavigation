import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Input, Radio, Select, Space } from 'antd';
import { useEffect, useMemo } from 'react';
import type { ResponseAssertMode, ResponseAssertRule } from '../utils/responseAssert';
import {
  ASSERT_CONNECTOR_OPTIONS,
  ASSERT_OPERATOR_OPTIONS,
  RESPONSE_ASSERT_MODE_OPTIONS,
  createEmptyRule,
  operatorNeedsRange,
  operatorNeedsValue,
  parseAssertRules,
  serializeAssertRules,
} from '../utils/responseAssert';
import './ResponseAssertEditor.css';

interface Props {
  mode: ResponseAssertMode;
  expectedText?: string;
  rulesText?: string;
  onModeChange: (mode: ResponseAssertMode) => void;
  onExpectedTextChange: (value: string) => void;
  onRulesTextChange: (value: string) => void;
}

export default function ResponseAssertEditor({
  mode,
  expectedText,
  rulesText,
  onModeChange,
  onExpectedTextChange,
  onRulesTextChange,
}: Props) {
  const rules = useMemo(() => parseAssertRules(rulesText), [rulesText]);

  useEffect(() => {
    if (mode === 'jsonpath' && !rulesText?.trim()) {
      onRulesTextChange(serializeAssertRules([createEmptyRule()]));
    }
  }, [mode, onRulesTextChange, rulesText]);

  const updateRules = (nextRules: ResponseAssertRule[]) => {
    onRulesTextChange(serializeAssertRules(nextRules.length ? nextRules : [createEmptyRule()]));
  };

  const updateRule = (id: string, patch: Partial<ResponseAssertRule>) => {
    updateRules(rules.map((rule) => (rule.id === id ? { ...rule, ...patch } : rule)));
  };

  const addRule = () => {
    updateRules([...rules, createEmptyRule()]);
  };

  const removeRule = (id: string) => {
    if (rules.length <= 1) {
      updateRules([createEmptyRule()]);
      return;
    }
    updateRules(rules.filter((rule) => rule.id !== id));
  };

  return (
    <div className="response-assert-editor">
      <div className="response-assert-editor__toolbar">
        <Radio.Group
          size="small"
          optionType="button"
          buttonStyle="solid"
          value={mode}
          options={RESPONSE_ASSERT_MODE_OPTIONS}
          onChange={(event) => onModeChange(event.target.value as ResponseAssertMode)}
        />
      </div>

      <div className="response-assert-editor__body">
        {mode === 'text' ? (
          <Input.TextArea
            className="response-assert-editor__textarea"
            value={expectedText}
            onChange={(event) => onExpectedTextChange(event.target.value)}
            placeholder='文本校验：响应体需完全一致（JSON 会做结构等价比较），例如 {"code":0,"message":"success"}'
          />
        ) : (
          <>
            <div className="response-assert-editor__rules">
              {rules.map((rule, index) => (
                <div className="response-assert-editor__rule" key={rule.id}>
                  {index > 0 ? (
                    <Select
                      size="small"
                      className="response-assert-editor__connector"
                      value={rules[index - 1].connector || 'and'}
                      options={ASSERT_CONNECTOR_OPTIONS}
                      onChange={(value) => updateRule(rules[index - 1].id, { connector: value })}
                    />
                  ) : (
                    <span className="response-assert-editor__connector-placeholder" />
                  )}
                  <Input
                    size="small"
                    className="response-assert-editor__path"
                    value={rule.path}
                    placeholder="关键值校验：JSONPath，如 $.data.code"
                    onChange={(event) => updateRule(rule.id, { path: event.target.value })}
                  />
                  <Select
                    size="small"
                    className="response-assert-editor__operator"
                    value={rule.operator}
                    options={ASSERT_OPERATOR_OPTIONS}
                    onChange={(value) => updateRule(rule.id, { operator: value })}
                  />
                  {operatorNeedsValue(rule.operator) ? (
                    operatorNeedsRange(rule.operator) ? (
                      <Space size={4} className="response-assert-editor__range">
                        <Input
                          size="small"
                          value={rule.expected}
                          placeholder="最小值"
                          onChange={(event) => updateRule(rule.id, { expected: event.target.value })}
                        />
                        <span>~</span>
                        <Input
                          size="small"
                          value={rule.expectedTo}
                          placeholder="最大值"
                          onChange={(event) => updateRule(rule.id, { expectedTo: event.target.value })}
                        />
                      </Space>
                    ) : (
                      <Input
                        size="small"
                        className="response-assert-editor__expected"
                        value={rule.expected}
                        placeholder="预期值"
                        onChange={(event) => updateRule(rule.id, { expected: event.target.value })}
                      />
                    )
                  ) : (
                    <span className="response-assert-editor__expected-placeholder" />
                  )}
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => removeRule(rule.id)}
                  />
                </div>
              ))}
            </div>
            <Button
              type="dashed"
              size="small"
              className="response-assert-editor__add-rule"
              icon={<PlusOutlined />}
              onClick={addRule}
            >
              新增规则
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
