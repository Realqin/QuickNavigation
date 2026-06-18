import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  App,
  AutoComplete,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  createLlmConfig,
  deleteLlmConfig,
  fetchLlmModels,
  fetchLlmConfigs,
  testLlmConnection,
  toggleLlmConfig,
  updateLlmConfig,
} from '../api';
import type { LlmConfig, LlmConfigFormValues } from '../types/llm';
import { formatBeijingTime } from '../utils/dateTime';

const DEFAULT_FORM: LlmConfigFormValues = {
  name: '',
  api_url: '',
  api_key: '',
  model_name: '',
  context_limit: 128000,
  vision_enabled: false,
  stream_enabled: true,
  enabled: false,
};

export default function LlmConfigPage() {
  const { message } = App.useApp();
  const [items, setItems] = useState<LlmConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<LlmConfig | null>(null);
  const [testing, setTesting] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [testMessage, setTestMessage] = useState('');
  const [form] = Form.useForm<LlmConfigFormValues>();

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchLlmConfigs());
    } catch {
      message.error('加载 LLM 配置失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue(DEFAULT_FORM);
    setModelOptions([]);
    setTestMessage('');
    setModalOpen(true);
  };

  const openEdit = (item: LlmConfig) => {
    setEditing(item);
    form.setFieldsValue({
      name: item.name,
      api_url: item.api_url,
      api_key: '',
      model_name: item.model_name,
      context_limit: item.context_limit,
      vision_enabled: item.vision_enabled,
      stream_enabled: item.stream_enabled,
      enabled: item.enabled,
    });
    setModelOptions(item.model_name ? [item.model_name] : []);
    setTestMessage('');
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await updateLlmConfig(editing.id, values);
        message.success('更新成功');
      } else {
        await createLlmConfig(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      setEditing(null);
      await loadItems();
    } catch {
      message.error('保存失败');
    }
  };

  const handleDelete = async (item: LlmConfig) => {
    try {
      await deleteLlmConfig(item.id);
      message.success('删除成功');
      await loadItems();
    } catch {
      message.error('删除失败');
    }
  };

  const handleToggle = async (item: LlmConfig) => {
    try {
      await toggleLlmConfig(item.id, !item.enabled);
      await loadItems();
    } catch {
      message.error('切换状态失败');
    }
  };

  const handleFetchModels = async () => {
    const values = form.getFieldsValue();
    if (!values.api_url || (!editing && !values.api_key)) {
      message.warning('请先填写 API URL 和 API Key');
      return;
    }
    setLoadingModels(true);
    setTestMessage('');
    try {
      const result = await fetchLlmModels({
        api_url: values.api_url,
        api_key: values.api_key,
        config_id: editing?.id ?? null,
      });
      const nextOptions = result.items || [];
      setModelOptions(nextOptions);
      if (nextOptions.length > 0 && !nextOptions.includes(values.model_name)) {
        form.setFieldValue('model_name', nextOptions[0]);
      }
      const successText = `已成功拉取 ${nextOptions.length} 个模型`;
      setTestMessage(successText);
      message.success(successText);
    } catch (error) {
      const axiosError = error as { code?: string; message?: string; response?: { data?: { detail?: string } } };
      if (axiosError.code === 'ECONNABORTED') {
        const timeoutText = '拉取模型列表超时（90 秒），请稍后重试';
        setTestMessage(timeoutText);
        message.error(timeoutText);
      } else {
        const detail =
          axiosError.response?.data?.detail ||
          axiosError.message ||
          '拉取模型列表失败';
        setTestMessage(String(detail));
        message.error(String(detail));
      }
    } finally {
      setLoadingModels(false);
    }
  };

  const handleTestConnection = async () => {
    const values = await form.validateFields(['api_url', 'model_name']);
    const apiKey = form.getFieldValue('api_key') as string;
    if (!editing && !apiKey) {
      message.warning('请先填写 API Key');
      return;
    }
    setTesting(true);
    setTestMessage('');
    try {
      const result = await testLlmConnection({
        api_url: values.api_url,
        api_key: apiKey,
        model_name: values.model_name,
        config_id: editing?.id ?? null,
      });
      const successText = result.message || '测试连接成功';
      setTestMessage(successText);
      message.success(successText);
    } catch (error) {
      const axiosError = error as { code?: string; message?: string; response?: { data?: { detail?: string } } };
      if (axiosError.code === 'ECONNABORTED') {
        const timeoutText = '测试连接超时（90 秒），请检查 LLM 服务是否可达或网络是否较慢';
        setTestMessage(timeoutText);
        message.error(timeoutText);
      } else {
        const detail =
          axiosError.response?.data?.detail ||
          axiosError.message ||
          '测试连接失败';
        setTestMessage(String(detail));
        message.error(String(detail));
      }
    } finally {
      setTesting(false);
    }
  };

  const modelAutoOptions = useMemo(
    () => modelOptions.map((model) => ({ value: model })),
    [modelOptions],
  );

  const columns: ColumnsType<LlmConfig> = [
    {
      title: '序号',
      width: 70,
      render: (_value, _record, index) => index + 1,
    },
    { title: '配置名称', dataIndex: 'name', width: 140 },
    { title: '模型名称', dataIndex: 'model_name', width: 160 },
    {
      title: 'API URL',
      dataIndex: 'api_url',
      width: 200,
      ellipsis: true,
      render: (value: string) => (
        <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 180 }}>
          {value || '-'}
        </Typography.Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 110,
      render: (enabled: boolean, record) => (
        <Switch checked={enabled} checkedChildren="已激活" unCheckedChildren="未激活" onChange={() => handleToggle(record)} />
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value?: string | null) => formatBeijingTime(value) || '-',
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: (value?: string | null) => formatBeijingTime(value) || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      fixed: 'right',
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm title="确认删除该配置？" onConfirm={() => handleDelete(record)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="admin-page">
      <div className="admin-page__header">
        <Typography.Title level={4} className="admin-page__title">
          LLM 配置管理
        </Typography.Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadItems()} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增配置
          </Button>
        </Space>
      </div>

      <Table
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={items}
        pagination={false}
        scroll={{ x: 1100 }}
        locale={{ emptyText: '暂无 LLM 配置' }}
      />

      <Modal
        title={editing ? '编辑 LLM 配置' : '新增 LLM 配置'}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onOk={handleSubmit}
        okText="保存"
        cancelText="取消"
        width={720}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" size="small" className="admin-form-modal">
          <Form.Item name="name" label="配置名称" rules={[{ required: true, message: '请输入配置名称' }]}>
            <Input placeholder="例如 qwen / glm" />
          </Form.Item>
          <Form.Item name="api_url" label="API URL" rules={[{ required: true, message: '请输入 API URL' }]}>
            <Input placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            rules={editing ? [] : [{ required: true, message: '请输入 API Key' }]}
            extra={
              editing
                ? '留空则使用已保存的 Key；测试连接/拉取模型会通过 config_id 在后端读取，不会把 Key 传回浏览器'
                : undefined
            }
          >
            <Input.Password placeholder={editing ? '留空不修改' : '请输入 API Key'} />
          </Form.Item>
          <Space align="start" style={{ width: '100%' }} size={12}>
            <Form.Item
              name="model_name"
              label="模型名称"
              rules={[{ required: true, message: '请输入或选择模型' }]}
              style={{ flex: 1, minWidth: 280 }}
            >
              <AutoComplete options={modelAutoOptions} placeholder="输入或选择模型" />
            </Form.Item>
            <Form.Item label=" ">
              <Space>
                <Button loading={loadingModels} onClick={handleFetchModels}>
                  刷新模型
                </Button>
                <Button loading={testing} onClick={handleTestConnection}>
                  测试连接
                </Button>
              </Space>
            </Form.Item>
          </Space>
          {testMessage ? (
            <Typography.Paragraph type="secondary" style={{ marginTop: -8 }}>
              {testMessage}
            </Typography.Paragraph>
          ) : null}
          <Space size={16} wrap style={{ width: '100%' }}>
            <Form.Item
              name="context_limit"
              label="上下文限制"
              extra="模型上下文窗口上限（tokens）。实际调用时会据此自动截断过长输入，并限制单次输出 max_tokens。"
            >
              <InputNumber min={1} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="vision_enabled" label="多模态 Vision" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="stream_enabled" label="流式输出 Stream" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="enabled" label="设为激活配置" valuePropName="checked">
              <Switch checkedChildren="激活" unCheckedChildren="关闭" />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
