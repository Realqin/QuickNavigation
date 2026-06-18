import { ApiOutlined, MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, Input, InputNumber, Modal, Select, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { testConnection } from '../api';
import type { Connection, ConnectionFormValues, DictItem } from '../types';
import {
  DEFAULT_PORTS,
  LABEL_KAFKA,
  resolveConnectionKind,
  supportsConnectionTest,
  type ConnectionKind,
} from '../utils/connectionType';
import {
  formatKafkaBrokersForInput,
  normalizeKafkaBrokersInput,
} from '../utils/kafkaBrokers';
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
  if (kind === 'kafka') {
    return (
      <>
        <Form.Item
          name="host"
          label="集群地址"
          rules={[{ required: true, message: '请输入 Kafka 集群地址' }]}
          extra="多个节点用英文逗号分隔，格式：IP:端口"
        >
          <Input placeholder="10.100.0.211:9092,10.100.0.212:9092,10.100.0.213:9092" />
        </Form.Item>
        <Form.Item name="username" label="用户名">
          <Input placeholder="可选，SASL 认证" />
        </Form.Item>
        <Form.Item name="password" label="密码">
          <Input.Password
            placeholder={passwordSet ? '已设置，留空不修改' : '可选，SASL 认证'}
            autoComplete="new-password"
          />
        </Form.Item>
        <div className="connection-form-modal__test-btn">
          <Button icon={<ApiOutlined />} loading={testing} onClick={onTest}>
            测试连接
          </Button>
        </div>
      </>
    );
  }

  if (kind === 'mqtt') {
    return (
      <>
        <Form.Item label="连接地址" required extra="连接格式为mqtt://主机:端口">
          <div className="connection-form-modal__endpoint-row">
            <div className="connection-form-modal__endpoint-host">
              <Form.Item
                name="host"
                noStyle
                rules={[{ required: true, message: '请输入连接地址' }]}
              >
                <Input placeholder="10.100.0.230" />
              </Form.Item>
            </div>
            <span className="connection-form-modal__endpoint-sep">:</span>
            <div className="connection-form-modal__endpoint-port">
              <Form.Item
                name="port"
                noStyle
                rules={[{ required: true, message: '请输入端口' }]}
              >
                <InputNumber min={1} max={65535} placeholder="1883" />
              </Form.Item>
            </div>
          </div>
        </Form.Item>
        <Form.Item name="username" label="用户名">
          <Input placeholder="可选" />
        </Form.Item>
        <Form.Item name="password" label="密码">
          <Input.Password
            placeholder={passwordSet ? '已设置，留空不修改' : '可选'}
            autoComplete="new-password"
          />
        </Form.Item>
        <Form.List name="mqtt_subscriptions">
          {(fields, { add, remove }) => (
            <>
              <div className="connection-form-modal__mqtt-sub-title">预置订阅</div>
              {fields.map(({ key, name, ...restField }) => (
                <div key={key} className="connection-form-modal__sub-link-row">
                  <Form.Item
                    {...restField}
                    name={[name, 'name']}
                    className="connection-form-modal__sub-link-name"
                  >
                    <Input placeholder="备注名（可选）" />
                  </Form.Item>
                  <Form.Item
                    {...restField}
                    name={[name, 'topic']}
                    rules={[{ required: true, message: 'Topic' }]}
                    className="connection-form-modal__sub-link-url"
                  >
                    <Input placeholder="sensor/temperature" />
                  </Form.Item>
                  <MinusCircleOutlined
                    onClick={() => remove(name)}
                    style={{ color: '#ff4d4f', marginTop: 8 }}
                  />
                </div>
              ))}
              <Button
                type="dashed"
                onClick={() => add({ topic: '', name: '' })}
                icon={<PlusOutlined />}
                className="connection-form-modal__sub-link-add"
              >
                添加订阅项
              </Button>
            </>
          )}
        </Form.List>
        <div className="connection-form-modal__test-btn">
          <Button icon={<ApiOutlined />} loading={testing} onClick={onTest}>
            测试连接
          </Button>
        </div>
      </>
    );
  }

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

  if (kind === 'gitlab') {
    return (
      <>
        <Form.Item
          name="url"
          label="仓库 URL"
          rules={[{ required: true, message: '请输入仓库浏览地址' }]}
          extra="GitLab 项目浏览地址，需包含分支，如 .../-/tree/main"
        >
          <Input placeholder="https://gitlab.example.com/group/project/-/tree/main" />
        </Form.Item>
        <Form.Item
          name="host"
          label="Clone 地址"
          extra="可选，支持 SSH（git@...）或 HTTPS 格式；用于 git clone 拉取代码"
        >
          <Input placeholder="git@gitlab.example.com:group/project.git 或 https://gitlab.example.com/group/project.git" />
        </Form.Item>
        <Form.List name="sub_links">
          {(fields, { add, remove }) => (
            <div className="connection-form-modal__gitlab-sub-section">
              <div className="connection-form-modal__gitlab-sub-header">
                <span>子项名称</span>
                <span>仓库地址</span>
                <span>Clone 地址</span>
                <span className="connection-form-modal__gitlab-sub-header-action" />
              </div>
              {fields.map(({ key, name, ...restField }) => (
                <div key={key} className="connection-form-modal__gitlab-sub-link-row">
                  <Form.Item
                    {...restField}
                    name={[name, 'name']}
                    rules={[{ required: true, message: '请输入子项名称' }]}
                  >
                    <Input placeholder="子项名称" />
                  </Form.Item>
                  <Form.Item
                    {...restField}
                    name={[name, 'url']}
                    rules={[{ required: true, message: '请输入仓库地址' }]}
                  >
                    <Input placeholder="https://.../-/tree/main" />
                  </Form.Item>
                  <Form.Item {...restField} name={[name, 'clone_url']}>
                    <Input placeholder="git@... 或 https://..." />
                  </Form.Item>
                  <MinusCircleOutlined
                    className="connection-form-modal__gitlab-sub-remove"
                    onClick={() => remove(name)}
                  />
                </div>
              ))}
              <Button
                type="dashed"
                block
                onClick={() => add({ name: '', url: '', clone_url: '' })}
                icon={<PlusOutlined />}
                className="connection-form-modal__gitlab-sub-add"
              >
                添加子项
              </Button>
            </div>
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
      {kind !== 'redis' && kind !== 'mqtt' && kind !== 'kafka' ? (
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
        const editKind = resolveConnectionKind(connection.type, labelItems);
        form.setFieldsValue({
          name: connection.name,
          url: connection.url,
          description: connection.description ?? undefined,
          projects: connection.projects ?? [],
          environments: connection.environments ?? [],
          type: connection.type,
          group_id: connection.group_id ?? projectGroupId,
          sub_links: connection.sub_links ?? [],
          host:
            editKind === 'kafka'
              ? formatKafkaBrokersForInput(connection.host, connection.port)
              : (connection.host ?? undefined),
          port:
            editKind === 'kafka' || editKind === 'gitlab'
              ? undefined
              : (connection.port ?? DEFAULT_PORTS[editKind]),
          username: connection.username ?? undefined,
          password: '',
          database_name: connection.database_name ?? undefined,
          mqtt_ws_path: connection.mqtt_ws_path ?? '/mqtt',
          mqtt_subscriptions: connection.mqtt_subscriptions ?? [],
        });
      } else {
        const kafkaTypeId = labelItems.find((item) => item.name === LABEL_KAFKA)?.id;
        const initialType = defaultType ?? kafkaTypeId ?? labelOptions[0]?.value;
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
          mqtt_subscriptions: [],
          mqtt_ws_path: '/mqtt',
          host: initialKind === 'kafka' ? '' : undefined,
          port: initialKind === 'kafka' ? undefined : DEFAULT_PORTS[initialKind],
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
    if (!open || connection || connectionKind === 'kafka' || connectionKind === 'gitlab' || connectionKind === 'other') {
      return;
    }
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
          : connectionKind === 'mqtt'
            ? (['type', 'host', 'port', 'username', 'password'] as const)
            : connectionKind === 'kafka'
              ? (['type', 'host', 'username', 'password'] as const)
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
        host:
          connectionKind === 'kafka'
            ? normalizeKafkaBrokersInput(values.host?.trim() ?? '')
            : (values.host?.trim() ?? ''),
        port: connectionKind === 'kafka' ? undefined : Number(values.port),
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
    } else if (connectionKind === 'gitlab') {
      payload.sub_links = (values.sub_links ?? []).filter(
        (item) => item?.name?.trim() && item?.url?.trim(),
      );
      payload.host = values.host?.trim() || '';
      payload.port = undefined;
      payload.username = undefined;
      payload.password = undefined;
    } else if (connectionKind === 'mqtt') {
      payload.url = '';
      payload.sub_links = [];
      payload.mqtt_subscriptions = (values.mqtt_subscriptions ?? []).filter(
        (item) => item?.topic?.trim(),
      );
      if (!payload.password?.trim()) {
        delete payload.password;
      }
    } else if (connectionKind === 'kafka') {
      payload.url = '';
      payload.sub_links = [];
      payload.host = normalizeKafkaBrokersInput(values.host?.trim() ?? '');
      payload.port = undefined;
      if (!payload.password?.trim()) {
        delete payload.password;
      }
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
          : connectionKind === 'mqtt'
            ? connection
              ? '编辑 MQTT 连接'
              : '新增 MQTT 连接'
            : connectionKind === 'kafka'
              ? connection
                ? '编辑 Kafka 连接'
                : '新增 Kafka 连接'
              : connectionKind === 'gitlab'
                ? connection
                  ? '编辑 GitLab 连接'
                  : '新增 GitLab 连接'
                : connection
            ? '编辑连接'
            : '新增连接';

  const modalWidth =
    connectionKind === 'gitlab' ? 880 : connectionKind === 'other' ? 540 : 460;

  return (
    <Modal
      title={modalTitle}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      destroyOnHidden
      width={modalWidth}
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
