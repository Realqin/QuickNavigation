import { ApiOutlined } from '@ant-design/icons';
import { App, Button, Form, Input, Modal } from 'antd';
import { useCallback, useMemo, useState } from 'react';
import { testKafkaConsoleConnection } from '../api';
import type { KafkaConsoleConnection, KafkaConsoleConnectionFormValues } from '../types';
import { normalizeKafkaBrokersInput } from '../utils/kafkaBrokers';
import { showApiError } from '../utils/apiError';
import './ConnectionFormModal.css';

interface Props {
  open: boolean;
  connection?: KafkaConsoleConnection | null;
  onCancel: () => void;
  onSubmit: (values: KafkaConsoleConnectionFormValues) => Promise<void>;
}

const formLayout = {
  labelCol: { flex: '84px' },
  wrapperCol: { flex: 'auto' },
};

export default function KafkaConsoleConnectionModal({
  open,
  connection,
  onCancel,
  onSubmit,
}: Props) {
  const { message } = App.useApp();
  const [form] = Form.useForm<KafkaConsoleConnectionFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);

  const formKey = connection ? `edit-${connection.id}` : 'create';

  const initialValues = useMemo<KafkaConsoleConnectionFormValues>(
    () =>
      connection
        ? {
            name: connection.name,
            brokers: connection.brokers,
            username: connection.username ?? '',
            password: '',
          }
        : {
            name: '',
            brokers: '',
            username: '',
            password: '',
          },
    [connection],
  );

  const fillFormValues = useCallback(() => {
    if (connection) {
      form.setFieldsValue({
        name: connection.name,
        brokers: connection.brokers,
        username: connection.username ?? '',
        password: '',
      });
      return;
    }
    form.resetFields();
  }, [connection, form]);

  const handleTest = async () => {
    const values = await form.validateFields(['brokers', 'username', 'password']);
    setTesting(true);
    try {
      const result = await testKafkaConsoleConnection({
        brokers: normalizeKafkaBrokersInput(values.brokers?.trim() ?? ''),
        username: values.username?.trim() || undefined,
        password: values.password?.trim() || undefined,
      });
      if (result.ok) {
        message.success(
          result.latency_ms != null ? `${result.message}（${result.latency_ms}ms）` : result.message,
        );
      } else {
        message.error(result.message);
      }
    } catch (error) {
      showApiError(error, '测试连接失败');
    } finally {
      setTesting(false);
    }
  };

  const handleOk = async () => {
    const values = await form.validateFields();
    const payload: KafkaConsoleConnectionFormValues = {
      name: values.name.trim(),
      brokers: normalizeKafkaBrokersInput(values.brokers.trim()),
      username: values.username?.trim() || undefined,
    };
    const password = values.password?.trim();
    if (password || !connection?.password_set) {
      payload.password = password || undefined;
    }
    setSubmitting(true);
    try {
      await onSubmit(payload);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={connection ? '编辑 Kafka 连接' : '新增 Kafka 连接'}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={submitting}
      destroyOnHidden
      afterOpenChange={(visible) => {
        if (visible) {
          fillFormValues();
        }
      }}
      width={520}
      className="connection-form-modal"
    >
      <Form
        key={open ? formKey : 'closed'}
        form={form}
        {...formLayout}
        layout="horizontal"
        initialValues={initialValues}
      >
        <Form.Item
          name="name"
          label="连接名称"
          rules={[{ required: true, message: '请输入连接名称' }]}
        >
          <Input placeholder="例如：生产 Kafka 集群" />
        </Form.Item>
        <Form.Item
          name="brokers"
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
            placeholder={connection?.password_set ? '已设置，留空不修改' : '可选，SASL 认证'}
            autoComplete="new-password"
          />
        </Form.Item>
        <div className="connection-form-modal__test-btn">
          <Button icon={<ApiOutlined />} loading={testing} onClick={handleTest}>
            测试连接
          </Button>
        </div>
      </Form>
    </Modal>
  );
}
