import { ApiOutlined, MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, Input, InputNumber, Modal, Select, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { testConnection } from '../api';
import type { Connection, ConnectionFormValues, DictItem } from '../types';
import {
  DEFAULT_PORTS,
  resolveConnectionKind,
  supportsConnectionTest,
  type ConnectionKind,
} from '../utils/connectionType';
import './ConnectionFormModal.css';

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
  labelItems: DictItem[];
  groupOptions: SelectOption[];
  groupItems: DictItem[];
  defaultProjects?: number[];
  defaultEnvironments?: number[];
  defaultType?: number;
  defaultGroupId?: number;
  onCancel: () => void;
  onSubmit: (values: ConnectionFormValues) => Promise<void>;
}

const formLayout = {
  labelCol: { flex: '84px' },
  wrapperCol: { flex: 'auto' },
};

function TypeFields({
  kind,
  passwordSet,
  testing,
  onTest,
}: {
  kind: ConnectionKind;
  passwordSet: boolean;
  testing: boolean;
  onTest: () => void;
}) {
  if (kind === 'other') {
    return (
      <>
        <Form.Item name="url" label="主 URL" rules={[{ required: true, message: '请输入 URL' }]}>
          <Input placeholder="https://..." />
        </Form.Item>
        <Form.List name="sub_links">
          {(fields, { add, remove }) => (
            <>
              {fields.map(({ key, name, ...restField }) => (
                <div key={key} className="connection-form-modal__sub-link-row">
                  <Form.Item
                    {...restField}
                    name={[name, 'name']}
                    rules={[{ required: true, message: '名称' }]}
                    className="connection-form-modal__sub-link-name"
                  >
                    <Input placeholder="子项名称" />
                  </Form.Item>
                  <Form.Item
                    {...restField}
                    name={[name, 'url']}
                    rules={[{ required: true, message: 'URL' }]}
                    className="connection-form-modal__sub-link-url"
                  >
                    <Input placeholder="子项 URL" />
                  </Form.Item>
                  <MinusCircleOutlined onClick={() => remove(name)} style={{ color: '#ff4d4f', marginTop: 8 }} />
                </div>
              ))}
              <Button
                type="dashed"
                onClick={() => add()}
                icon={<PlusOutlined />}
                className="connection-form-modal__sub-link-add"
              >
                添加子链接
              </Button>
            </>
          )}
        </Form.List>
      </>
    );
  }

  const passwordPlaceholder =
    kind === 'database'
      ? passwordSet
        ? '已设置，留空不修改'
        : '可选'
      : passwordSet
        ? '已设置，留空不修改'
        : kind === 'terminal'
          ? '请输入密码'
          : '可选';

  return (
    <>
      <Form.Item name="host" label="主机" rules={[{ required: true, message: '请输入主机' }]}>
        <Input placeholder="localhost" />
      </Form.Item>
      <Form.Item name="port" label="端口" rules={[{ required: true, message: '请输入端口' }]}>
        <InputNumber min={1} max={65535} className="connection-form-modal__port" />
      </Form.Item>
      {kind !== 'redis' ? (
        <Form.Item
          name="username"
          label={kind === 'database' ? '用户名' : '账号'}
          rules={[{ required: true, message: kind === 'database' ? '请输入用户名' : '请输入账号' }]}
        >
          <Input placeholder={kind === 'database' ? 'root' : '账号'} />
        </Form.Item>
      ) : null}
      <Form.Item
        name="password"
        label="密码"
        rules={
          kind === 'terminal' && !passwordSet
            ? [{ required: true, message: '请输入密码' }]
            : []
        }
      >
        <Input.Password placeholder={passwordPlaceholder} autoComplete="new-password" />
      </Form.Item>
      {kind === 'database' ? (
        <Form.Item name="database_name" label="数据库">
          <Input placeholder="可选，如：app_db" />
        </Form.Item>
      ) : null}
      {supportsConnectionTest(kind) ? (
        <div className="connection-form-modal__test-btn">
          <Button icon={<ApiOutlined />} loading={testing} onClick={onTest}>
            测试连接
          </Button>
        </div>
      ) : null}
    </>
  );
}

export default function ConnectionFormModal({
  open,
  connection,
  projectOptions,
  environmentOptions,
  labelOptions,
  labelItems,
  groupOptions,
  groupItems,
  defaultProjects,
  defaultEnvironments,
  defaultType,
  defaultGroupId,
  onCancel,
  onSubmit,
}: Props) {
  const [form] = Form.useForm<ConnectionFormValues>();
  const [testing, setTesting] = useState(false);
  const selectedType = Form.useWatch('type', form);

  const projectGroupId = useMemo(
    () => groupItems.find((item) => item.is_system)?.id,
    [groupItems],
  );

  const connectionKind = useMemo(
    () => resolveConnectionKind(selectedType, labelItems),
    [selectedType, labelItems],
  );

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
          group_id: connection.group_id ?? projectGroupId,
          sub_links: connection.sub_links ?? [],
          host: connection.host ?? undefined,
          port: connection.port ?? DEFAULT_PORTS[resolveConnectionKind(connection.type, labelItems)],
          username: connection.username ?? undefined,
          password: '',
          database_name: connection.database_name ?? undefined,
        });
      } else {
        const initialType = defaultType ?? labelOptions[0]?.value;
        const initialKind = resolveConnectionKind(initialType, labelItems);
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
          type: initialType,
          group_id: defaultGroupId ?? projectGroupId ?? groupOptions[0]?.value,
          sub_links: [],
          port: DEFAULT_PORTS[initialKind],
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
    labelItems,
    groupOptions,
    projectGroupId,
    defaultProjects,
    defaultEnvironments,
    defaultType,
    defaultGroupId,
  ]);

  useEffect(() => {
    if (!open || connection) return;
    const defaultPort = DEFAULT_PORTS[connectionKind];
    if (defaultPort != null) {
      form.setFieldValue('port', defaultPort);
    }
  }, [open, connection, connectionKind, form]);

  const handleTest = async () => {
    const fields =
      connectionKind === 'database'
        ? (['type', 'host', 'port', 'username', 'password'] as const)
        : connectionKind === 'terminal'
          ? (['type', 'host', 'port', 'username', 'password'] as const)
          : (['type', 'host', 'port', 'password'] as const);
    const values = await form.validateFields([...fields]);
    const password = values.password?.trim();
    if (!password && !connection?.password_set && connectionKind === 'terminal') {
      message.warning('测试终端连接前请先填写密码');
      return;
    }
    setTesting(true);
    try {
      const result = await testConnection({
        type: values.type,
        host: values.host?.trim() ?? '',
        port: Number(values.port),
        username: values.username?.trim() || undefined,
        password: password || undefined,
        database_name: values.database_name?.trim() || undefined,
      });
      if (result.ok) {
        message.success(
          result.latency_ms != null ? `${result.message}（${result.latency_ms}ms）` : result.message,
        );
      } else {
        message.error(result.message);
      }
    } catch {
      message.error('测试连接失败');
    } finally {
      setTesting(false);
    }
  };

  const handleOk = async () => {
    const values = await form.validateFields();
    const payload: ConnectionFormValues = { ...values };
    if (connectionKind === 'other') {
      payload.sub_links = (values.sub_links ?? []).filter(
        (item) => item?.name?.trim() && item?.url?.trim(),
      );
    } else {
      payload.url = '';
      payload.sub_links = [];
      if (!payload.password?.trim()) {
        delete payload.password;
      }
    }
    await onSubmit(payload);
    form.resetFields();
  };

  const modalTitle =
    connectionKind === 'database'
      ? connection
        ? '编辑数据库连接'
        : '新增数据库连接'
      : connectionKind === 'terminal'
        ? connection
          ? '编辑终端连接'
          : '新增终端连接'
        : connectionKind === 'redis'
          ? connection
            ? '编辑 Redis 连接'
            : '新增 Redis 连接'
          : connection
            ? '编辑连接'
            : '新增连接';

  return (
    <Modal
      title={modalTitle}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      destroyOnClose
      width={connectionKind === 'other' ? 540 : 460}
      className="connection-form-modal"
      styles={{ body: { paddingTop: 16, paddingBottom: 12 } }}
    >
      <Form
        form={form}
        layout="horizontal"
        colon={false}
        {...formLayout}
      >
        <Form.Item name="type" label="类型" rules={[{ required: true, message: '请选择类型' }]}>
          <Select options={labelOptions} placeholder="选择类型" />
        </Form.Item>
        <Form.Item name="name" label="连接名称" rules={[{ required: true, message: '请输入名称' }]}>
          <Input placeholder="连接名称" />
        </Form.Item>

        <TypeFields
          kind={connectionKind}
          passwordSet={Boolean(connection?.password_set)}
          testing={testing}
          onTest={() => {
            handleTest().catch(() => undefined);
          }}
        />

        <div className="connection-form-modal__section">
        <Form.Item name="group_id" label="分组" rules={[{ required: true, message: '请选择分组' }]}>
          <Select options={groupOptions} placeholder="选择分组" />
        </Form.Item>
        <Form.Item noStyle shouldUpdate={(prev, cur) => prev.group_id !== cur.group_id}>
          {({ getFieldValue }) =>
            getFieldValue('group_id') === projectGroupId ? (
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
                    placeholder="选择项目"
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
                    placeholder="选择环境"
                  />
                </Form.Item>
              </>
            ) : null
          }
        </Form.Item>
        <Form.Item name="description" label="描述">
          <Input placeholder="可选" />
        </Form.Item>
        </div>
      </Form>
    </Modal>
  );
}
