import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, Input, Modal, Select, Space, Switch, Typography } from 'antd';
import { useEffect } from 'react';
import type { Connection, ConnectionFormValues } from '../types';

interface SelectOption {
  label: string;
  value: number;
}

interface Props {
  open: boolean;
  connection?: Connection | null;
  projectOptions: SelectOption[];
  environmentOptions: SelectOption[];
  labelOptions: SelectOption[];
  defaultProjects?: number[];
  defaultEnvironments?: number[];
  defaultType?: number;
  onCancel: () => void;
  onSubmit: (values: ConnectionFormValues) => Promise<void>;
}

export default function ConnectionFormModal({
  open,
  connection,
  projectOptions,
  environmentOptions,
  labelOptions,
  defaultProjects,
  defaultEnvironments,
  defaultType,
  onCancel,
  onSubmit,
}: Props) {
  const [form] = Form.useForm<ConnectionFormValues>();

  useEffect(() => {
    if (open) {
      if (connection) {
        form.setFieldsValue({
          name: connection.name,
          url: connection.url,
          description: connection.description ?? undefined,
          projects: connection.projects ?? [],
          environments: connection.environments ?? [],
          type: connection.type,
          is_shared: connection.is_shared,
          sub_links: connection.sub_links ?? [],
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          projects: defaultProjects?.length
            ? defaultProjects
            : projectOptions[0]
              ? [projectOptions[0].value]
              : [],
          environments: defaultEnvironments?.length
            ? defaultEnvironments
            : environmentOptions[0]
              ? [environmentOptions[0].value]
              : [],
          type: defaultType ?? labelOptions[0]?.value,
          is_shared: false,
          sub_links: [],
        });
      }
    }
  }, [
    open,
    connection,
    form,
    projectOptions,
    environmentOptions,
    labelOptions,
    defaultProjects,
    defaultEnvironments,
    defaultType,
  ]);

  const handleOk = async () => {
    const values = await form.validateFields();
    const subLinks = (values.sub_links ?? []).filter(
      (item) => item?.name?.trim() && item?.url?.trim(),
    );
    await onSubmit({ ...values, sub_links: subLinks });
    form.resetFields();
  };

  return (
    <Modal
      title={connection ? '编辑连接' : '新增连接'}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      destroyOnClose
      width={640}
    >
      <Form form={form} layout="vertical">
        <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
          <Input placeholder="如：测试 API" />
        </Form.Item>
        <Form.Item name="url" label="主 URL" rules={[{ required: true, message: '请输入 URL' }]}>
          <Input placeholder="https://..." />
        </Form.Item>
        <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          点击卡片整体时跳转到主 URL；下方子链接可单独跳转各模块地址。
        </Typography.Text>
        <Form.Item name="description" label="描述">
          <Input.TextArea rows={2} placeholder="可选描述" />
        </Form.Item>
        <Form.Item name="is_shared" label="共用连接" valuePropName="checked">
          <Switch checkedChildren="是" unCheckedChildren="否" />
        </Form.Item>
        <Form.Item noStyle shouldUpdate={(prev, cur) => prev.is_shared !== cur.is_shared}>
          {({ getFieldValue }) =>
            !getFieldValue('is_shared') ? (
              <>
                <Form.Item
                  name="projects"
                  label="项目"
                  rules={[{ required: true, message: '请至少选择一个项目' }]}
                >
                  <Select
                    mode="multiple"
                    allowClear
                    options={projectOptions}
                    placeholder="选择一个或多个项目"
                  />
                </Form.Item>
                <Form.Item
                  name="environments"
                  label="环境"
                  rules={[{ required: true, message: '请至少选择一个环境' }]}
                >
                  <Select
                    mode="multiple"
                    allowClear
                    options={environmentOptions}
                    placeholder="选择一个或多个环境"
                  />
                </Form.Item>
              </>
            ) : null
          }
        </Form.Item>
        <Form.Item name="type" label="类型" rules={[{ required: true, message: '请选择类型' }]}>
          <Select options={labelOptions} placeholder="选择类型" />
        </Form.Item>

        <Typography.Text strong>子链接</Typography.Text>
        <Form.List name="sub_links">
          {(fields, { add, remove }) => (
            <>
              {fields.map(({ key, name, ...restField }) => (
                <Space key={key} align="baseline" style={{ display: 'flex', marginBottom: 8 }}>
                  <Form.Item
                    {...restField}
                    name={[name, 'name']}
                    rules={[{ required: true, message: '名称' }]}
                    style={{ marginBottom: 0, width: 160 }}
                  >
                    <Input placeholder="子项名称" />
                  </Form.Item>
                  <Form.Item
                    {...restField}
                    name={[name, 'url']}
                    rules={[{ required: true, message: 'URL' }]}
                    style={{ marginBottom: 0, flex: 1, minWidth: 280 }}
                  >
                    <Input placeholder="子项 URL" />
                  </Form.Item>
                  <MinusCircleOutlined onClick={() => remove(name)} style={{ color: '#ff4d4f' }} />
                </Space>
              ))}
              <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                添加子链接
              </Button>
            </>
          )}
        </Form.List>
      </Form>
    </Modal>
  );
}
