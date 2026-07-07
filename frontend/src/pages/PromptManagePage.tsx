import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  App,
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useState } from 'react';
import {
  createPromptTemplate,
  deletePromptTemplate,
  fetchPromptTemplates,
  togglePromptTemplate,
  updatePromptTemplate,
} from '../api';
import type { PromptTemplate, PromptTemplateFormValues } from '../types/prompt';
import {
  PROMPT_TYPE_OPTIONS,
  RESPONSE_TYPE_PRESETS,
  getResponseTypeLabel,
} from '../types/prompt';
import { showApiError } from '../utils/apiError';

const EMPTY_FORM: PromptTemplateFormValues = {
  prompt_type: PROMPT_TYPE_OPTIONS[0],
  name: '',
  description: '',
  base_content: '',
  response_type: '',
  response_format: '',
  enabled: true,
  is_default: false,
  is_preset: false,
};

export default function PromptManagePage() {
  const { message } = App.useApp();
  const [items, setItems] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<PromptTemplate | null>(null);
  const [form] = Form.useForm<PromptTemplateFormValues>();

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await fetchPromptTemplates());
    } catch (error) {
      showApiError(error, '加载提示词失败');
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
    form.setFieldsValue(EMPTY_FORM);
    setModalOpen(true);
  };

  const openEdit = (item: PromptTemplate) => {
    const responseType = item.response_type || '';
    const presetFormat =
      RESPONSE_TYPE_PRESETS.find((option) => option.value === responseType)?.format || '';
    setEditing(item);
    form.setFieldsValue({
      prompt_type: item.prompt_type,
      name: item.name,
      description: item.description,
      base_content: item.base_content || item.content,
      response_type: responseType,
      response_format: item.response_format || presetFormat,
      remark: item.remark,
      enabled: item.enabled,
      is_default: item.is_default,
      is_preset: item.is_preset,
    });
    setModalOpen(true);
  };

  const handleResponseTypeChange = (nextType: string) => {
    const preset = RESPONSE_TYPE_PRESETS.find((item) => item.value === nextType);
    form.setFieldsValue({
      response_type: nextType,
      response_format: preset?.format ?? form.getFieldValue('response_format'),
    });
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const payload: PromptTemplateFormValues = {
      ...values,
      remark: editing?.remark || values.remark || '',
      is_preset: editing?.is_preset || false,
    };
    try {
      if (editing) {
        await updatePromptTemplate(editing.id, payload);
        message.success('更新成功');
      } else {
        await createPromptTemplate(payload);
        message.success('创建成功');
      }
      setModalOpen(false);
      setEditing(null);
      await loadItems();
    } catch (error) {
      showApiError(error, '保存失败');
    }
  };

  const handleDelete = async (item: PromptTemplate) => {
    try {
      await deletePromptTemplate(item.id);
      message.success('删除成功');
      await loadItems();
    } catch (error) {
      showApiError(error, '删除失败');
    }
  };

  const handleToggle = async (item: PromptTemplate) => {
    try {
      await togglePromptTemplate(item.id, !item.enabled);
      await loadItems();
    } catch (error) {
      showApiError(error, '切换状态失败');
    }
  };

  const isPreset = Boolean(editing?.is_preset);
  const responseType = Form.useWatch('response_type', form);
  const isPresetJson = isPreset && ['json-object', 'json-array'].includes(responseType || '');

  const columns: ColumnsType<PromptTemplate> = [
    {
      title: '序号',
      width: 56,
      align: 'center',
      render: (_value, _record, index) => index + 1,
    },
    { title: '类型', dataIndex: 'prompt_type', width: 88, ellipsis: true },
    {
      title: '名称',
      dataIndex: 'name',
      width: 120,
      ellipsis: true,
      render: (value: string) => (
        <Typography.Text ellipsis={{ tooltip: value }}>{value || '-'}</Typography.Text>
      ),
    },
    {
      title: '提示词内容',
      dataIndex: 'base_content',
      width: 160,
      ellipsis: true,
      render: (_value, record) => {
        const text = record.base_content || record.content;
        return (
          <Typography.Text ellipsis={{ tooltip: text }}>{text || '-'}</Typography.Text>
        );
      },
    },
    {
      title: '返回类型',
      dataIndex: 'response_type',
      width: 96,
      ellipsis: true,
      render: (value: string) => getResponseTypeLabel(value),
    },
    {
      title: '返回格式',
      dataIndex: 'response_format',
      width: 150,
      ellipsis: true,
      render: (value: string) => (
        <Typography.Text ellipsis={{ tooltip: value }}>{value || '-'}</Typography.Text>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      width: 100,
      ellipsis: true,
      render: (value: string) => (
        <Typography.Text ellipsis={{ tooltip: value }}>{value || '未设置'}</Typography.Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 92,
      render: (enabled: boolean, record) => (
        <Switch
          checked={enabled}
          checkedChildren="启用"
          unCheckedChildren="停用"
          onChange={() => handleToggle(record)}
        />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 168,
      render: (_, record) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm title="确认删除该提示词？" onConfirm={() => handleDelete(record)}>
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
          提示词管理
        </Typography.Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadItems()} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增
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
        tableLayout="fixed"
        className="prompt-manage-table"
        locale={{ emptyText: '暂无提示词数据' }}
      />

      <Modal
        title={editing ? '编辑提示词' : '新增提示词'}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onOk={handleSubmit}
        okText="保存"
        cancelText="取消"
        width={760}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" size="small" className="admin-form-modal">
          <Form.Item name="prompt_type" label="提示词类型" rules={[{ required: true, message: '请选择类型' }]}>
            <Select options={PROMPT_TYPE_OPTIONS.map((item) => ({ value: item, label: item }))} />
          </Form.Item>
          <Form.Item name="name" label="提示词名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="请输入提示词名称" disabled={isPreset} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input placeholder="可选描述" />
          </Form.Item>
          <Form.Item
            name="base_content"
            label="提示词内容"
            rules={[{ required: true, message: '请输入提示词内容' }]}
          >
            <Input.TextArea rows={8} showCount maxLength={10000} />
          </Form.Item>
          <Form.Item name="response_type" label="返回类型">
            <Select
              disabled={isPreset}
              options={RESPONSE_TYPE_PRESETS.map((item) => ({ value: item.value, label: item.label }))}
              onChange={handleResponseTypeChange}
            />
          </Form.Item>
          <Form.Item name="response_format" label="返回格式">
            <Input.TextArea rows={6} showCount maxLength={10000} disabled={isPresetJson} />
          </Form.Item>
          {isPresetJson ? (
            <Typography.Text type="secondary">预制项且返回类型为 JSON 时，返回格式不可调整。</Typography.Text>
          ) : null}
          <Space size={16} wrap>
            <Form.Item name="enabled" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="is_default" label="设为默认" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
          <Form.Item name="remark" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="is_preset" hidden>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
