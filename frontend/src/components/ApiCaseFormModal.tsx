import { Form, Input, InputNumber, Modal, Select } from 'antd';
import { useCallback, useMemo } from 'react';
import type { ApiTestCase, ApiTestCaseFormValues, ResponseAssertMode } from '../types/apiTestCase';
import {
  API_TEST_CASE_TYPE_OPTIONS,
  HTTP_METHOD_OPTIONS,
} from '../types/apiTestCase';
import {
  buildCombinedRequestParamsField,
  formatCaseHeadersDisplay,
  formatJsonField,
  splitCombinedRequestParams,
} from '../utils/caseRequestParts';
import { createEmptyRule, serializeAssertRules } from '../utils/responseAssert';
import ResponseAssertEditor from './ResponseAssertEditor';
import './ApiCaseFormModal.css';

interface Props {
  open: boolean;
  editing: ApiTestCase | null;
  projectOptions: Array<{ value: number; label: string }>;
  environmentOptions: Array<{ value: number; label: string }>;
  initialValues?: Partial<ApiTestCaseFormValues>;
  hideContextFields?: boolean;
  onCancel: () => void;
  onSubmit: (values: ApiTestCaseFormValues) => Promise<void>;
}

function buildEditingValues(editing: ApiTestCase): ApiTestCaseFormValues {
  return {
    project_id: editing.project_id,
    environment_id: editing.environment_id,
    service: editing.service,
    name: editing.name,
    api_path: editing.api_path,
    method: editing.method,
    request_headers: formatJsonField(
      formatCaseHeadersDisplay(editing.request_headers, editing.request_params),
    ),
    request_params_combined: buildCombinedRequestParamsField(
      editing.request_params,
      editing.request_body,
    ),
    expected_status: editing.expected_status,
    expected_response: formatJsonField(editing.expected_response),
    response_assert_mode: (editing.response_assert_mode === 'jsonpath' ? 'jsonpath' : 'text') as ResponseAssertMode,
    response_assert_rules: editing.response_assert_rules || serializeAssertRules([createEmptyRule()]),
    case_type: editing.case_type,
    endpoint_id: editing.endpoint_id ?? undefined,
  };
}

function buildCreateValues(
  projectOptions: Array<{ value: number; label: string }> = [],
  environmentOptions: Array<{ value: number; label: string }> = [],
  initialValues?: Partial<ApiTestCaseFormValues>,
): Partial<ApiTestCaseFormValues> {
  return {
    method: 'GET',
    expected_status: 200,
    case_type: 'smoke',
    response_assert_mode: 'text',
    response_assert_rules: serializeAssertRules([createEmptyRule()]),
    project_id: projectOptions[0]?.value,
    environment_id: environmentOptions[0]?.value,
    ...initialValues,
  };
}

export default function ApiCaseFormModal({
  open,
  editing,
  projectOptions,
  environmentOptions,
  initialValues,
  hideContextFields = false,
  onCancel,
  onSubmit,
}: Props) {
  const [form] = Form.useForm<ApiTestCaseFormValues>();

  const formKey = editing ? `edit-${editing.id}` : 'create';

  const defaultValues = useMemo(
    () => buildCreateValues(projectOptions ?? [], environmentOptions ?? [], initialValues),
    [projectOptions, environmentOptions, initialValues],
  );

  const assertMode = Form.useWatch('response_assert_mode', form) || 'text';
  const expectedResponse = Form.useWatch('expected_response', form);
  const assertRules = Form.useWatch('response_assert_rules', form);

  const syncFormValues = useCallback(() => {
    if (editing) {
      form.setFieldsValue(buildEditingValues(editing));
      return;
    }
    form.resetFields();
    form.setFieldsValue(defaultValues);
  }, [defaultValues, editing, form]);

  const handleAfterOpenChange = useCallback(
    (visible: boolean) => {
      if (visible) {
        syncFormValues();
      }
    },
    [syncFormValues],
  );

  const handleOk = async () => {
    const values = await form.validateFields();
    const { request_params_combined, ...rest } = values;
    const splitParams = splitCombinedRequestParams(request_params_combined);
    await onSubmit({
      ...rest,
      request_params: splitParams.request_params,
      request_body: splitParams.request_body,
      response_assert_mode: values.response_assert_mode || 'text',
      response_assert_rules:
        values.response_assert_mode === 'jsonpath' ? values.response_assert_rules : '',
    });
  };

  return (
    <Modal
      title={editing ? '编辑用例' : '新增用例'}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      afterOpenChange={handleAfterOpenChange}
      width={920}
      destroyOnHidden
      okText="保存"
      cancelText="取消"
      className="api-case-form-modal"
    >
      <Form
        key={formKey}
        form={form}
        layout="vertical"
        size="small"
        preserve={false}
        initialValues={editing ? buildEditingValues(editing) : defaultValues}
      >
        {!hideContextFields ? (
          <div className="api-case-form-modal__row api-case-form-modal__context-row">
            <Form.Item
              name="project_id"
              label="项目"
              rules={[{ required: true, message: '请选择项目' }]}
            >
              <Select options={projectOptions ?? []} placeholder="选择项目" />
            </Form.Item>
            <Form.Item
              name="environment_id"
              label="环境"
              rules={[{ required: true, message: '请选择环境' }]}
            >
              <Select options={environmentOptions ?? []} placeholder="选择环境" />
            </Form.Item>
            <Form.Item
              name="service"
              label="服务"
              rules={[{ required: true, message: '请输入服务名' }]}
            >
              <Input placeholder="例如 hscp-alarm" />
            </Form.Item>
          </div>
        ) : (
          <>
            <Form.Item name="project_id" hidden>
              <InputNumber />
            </Form.Item>
            <Form.Item name="environment_id" hidden>
              <InputNumber />
            </Form.Item>
            <Form.Item name="service" hidden>
              <Input />
            </Form.Item>
          </>
        )}
        <Form.Item name="endpoint_id" hidden>
          <InputNumber />
        </Form.Item>
        <Form.Item
          name="name"
          label="用例名称"
          rules={[{ required: true, message: '请输入用例名称' }]}
        >
          <Input.TextArea
            className="api-case-form-modal__textarea api-case-form-modal__textarea--name"
            rows={2}
            placeholder="例如 导出系统日志-冒烟"
          />
        </Form.Item>
        <Form.Item
          name="api_path"
          label="接口地址"
          rules={[{ required: true, message: '请输入接口地址' }]}
        >
          <Input placeholder="/api/admin/system/exportSysLog" />
        </Form.Item>
        <div className="api-case-form-modal__row">
          <Form.Item
            name="method"
            label="请求方式"
            rules={[{ required: true, message: '请选择请求方式' }]}
          >
            <Select options={HTTP_METHOD_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="expected_status"
            label="预期响应码"
            rules={[{ required: true, message: '请输入预期响应码' }]}
          >
            <InputNumber min={100} max={599} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="case_type"
            label="用例类型"
            rules={[{ required: true, message: '请选择用例类型' }]}
          >
            <Select options={API_TEST_CASE_TYPE_OPTIONS} />
          </Form.Item>
        </div>
        <Form.Item name="request_headers" label="请求头">
          <Input.TextArea
            className="api-case-form-modal__textarea api-case-form-modal__textarea--headers"
            rows={4}
            placeholder='例如 {"Content-Type":"application/json","Authorization":"Bearer ${token}"}'
          />
        </Form.Item>
        <Form.Item name="response_assert_mode" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="expected_response" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="response_assert_rules" hidden>
          <Input />
        </Form.Item>
        <div className="api-case-form-modal__json-row">
          <Form.Item
            name="request_params_combined"
            label="请求参数"
            className="api-case-form-modal__json-panel"
          >
            <Input.TextArea
              className="api-case-form-modal__textarea api-case-form-modal__textarea--json-field"
              placeholder='Query/Path/Body JSON，例如 {"query":{"page":1},"body":{"name":"test"}}'
            />
          </Form.Item>
          <Form.Item
            label="预期响应结果"
            className="api-case-form-modal__json-panel api-case-form-modal__assert-item"
          >
            <ResponseAssertEditor
              mode={assertMode === 'jsonpath' ? 'jsonpath' : 'text'}
              expectedText={expectedResponse}
              rulesText={assertRules}
              onModeChange={(mode) => form.setFieldValue('response_assert_mode', mode)}
              onExpectedTextChange={(value) => form.setFieldValue('expected_response', value)}
              onRulesTextChange={(value) => form.setFieldValue('response_assert_rules', value)}
            />
          </Form.Item>
        </div>
      </Form>
    </Modal>
  );
}
