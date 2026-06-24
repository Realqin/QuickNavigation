import { ApiOutlined } from '@ant-design/icons';
import { App, Button, Form, Input, Modal, Select, Switch } from 'antd';
import { useCallback, useMemo, useState } from 'react';
import { connectK8sCluster, createK8sCluster, updateK8sCluster } from '../api';
import type { K8sClusterConfig, K8sClusterFormValues } from '../types/k8s';
import './ConnectionFormModal.css';

interface Props {
  open: boolean;
  cluster?: K8sClusterConfig | null;
  onCancel: () => void;
  onSaved: (cluster: K8sClusterConfig) => void;
}

const formLayout = {
  labelCol: { flex: '96px' },
  wrapperCol: { flex: 'auto' },
};

function getErrorMessage(error: unknown, fallback: string) {
  return (
    (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || fallback
  );
}

export default function K8sClusterFormModal({ open, cluster, onCancel, onSaved }: Props) {
  const { message } = App.useApp();
  const [form] = Form.useForm<K8sClusterFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);
  const authType = Form.useWatch('auth_type', form);

  const initialValues = useMemo<K8sClusterFormValues>(
    () =>
      cluster
        ? {
            name: cluster.name,
            api_server: cluster.api_server,
            provider: cluster.provider,
            auth_type: cluster.auth_type,
            username: cluster.username ?? '',
            password: '',
            verify_ssl: cluster.verify_ssl,
          }
        : {
            name: '',
            api_server: 'http://10.100.0.11:30880',
            provider: 'native',
            auth_type: 'password',
            username: '',
            password: '',
            verify_ssl: false,
          },
    [cluster],
  );

  const fillFormValues = useCallback(() => {
    form.setFieldsValue(initialValues);
  }, [form, initialValues]);

  const buildPayload = async () => {
    const values = await form.validateFields();
    const password = values.password?.trim();
    const payload: K8sClusterFormValues = {
      name: values.name.trim(),
      api_server: values.api_server.trim(),
      provider: values.provider,
      auth_type: values.auth_type,
      username: values.username?.trim() || undefined,
      verify_ssl: Boolean(values.verify_ssl),
    };
    if (password || !cluster?.password_set) {
      payload.password = password || undefined;
    }
    return payload;
  };

  const saveCluster = async () => {
    const payload = await buildPayload();
    if (cluster) {
      return updateK8sCluster(cluster.id, payload);
    }
    return createK8sCluster(payload);
  };

  const handleOk = async () => {
    setSubmitting(true);
    try {
      const saved = await saveCluster();
      message.success(cluster ? '更新成功' : '创建成功');
      onSaved(saved);
    } catch (error) {
      message.error(getErrorMessage(error, '保存 K8s 连接失败'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const saved = await saveCluster();
      const result = await connectK8sCluster(saved.id);
      const versionText = result.version ? `，版本 ${result.version}` : '';
      const latencyText = result.latency_ms != null ? `，${result.latency_ms}ms` : '';
      message.success(`${result.message}${versionText}${latencyText}`);
      onSaved(saved);
    } catch (error) {
      message.error(getErrorMessage(error, '测试 K8s 连接失败'));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Modal
      title={cluster ? '编辑 K8s 连接' : '新增 K8s 连接'}
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
      width={560}
      className="connection-form-modal"
    >
      <Form
        key={open ? cluster?.id ?? 'create' : 'closed'}
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
          <Input placeholder="例如：生产 K8s 集群" />
        </Form.Item>
        <Form.Item
          name="api_server"
          label="集群地址"
          rules={[{ required: true, message: '请输入集群访问地址' }]}
        >
          <Input placeholder="http://10.100.0.11:30880" />
        </Form.Item>
        <Form.Item name="provider" label="来源">
          <Select
            options={[
              { label: 'Kubernetes 原生', value: 'native' },
              { label: 'KubeSphere', value: 'kubesphere' },
              { label: 'Kuboard', value: 'kuboard' },
            ]}
          />
        </Form.Item>
        <Form.Item name="auth_type" label="认证方式">
          <Select
            options={[
              { label: '账号密码', value: 'password' },
              { label: 'Bearer Token', value: 'token' },
            ]}
          />
        </Form.Item>
        {authType !== 'token' ? (
          <Form.Item
            name="username"
            label="账号"
            rules={[{ required: true, message: '请输入账号' }]}
          >
            <Input placeholder="请输入集群账号" />
          </Form.Item>
        ) : null}
        <Form.Item
          name="password"
          label={authType === 'token' ? 'Token' : '密码'}
          rules={
            cluster?.password_set
              ? []
              : [{ required: true, message: authType === 'token' ? '请输入 Token' : '请输入密码' }]
          }
        >
          <Input.Password
            placeholder={
              cluster?.password_set
                ? '已设置，留空不修改'
                : authType === 'token'
                  ? '请输入 Bearer Token'
                  : '请输入密码'
            }
            autoComplete="new-password"
          />
        </Form.Item>
        <Form.Item
          name="verify_ssl"
          label="校验证书"
          valuePropName="checked"
          extra="内网自签证书或 HTTP 地址通常关闭即可"
        >
          <Switch />
        </Form.Item>
        <div className="connection-form-modal__test-btn">
          <Button icon={<ApiOutlined />} loading={testing} onClick={handleTest}>
            保存并测试连接
          </Button>
        </div>
      </Form>
    </Modal>
  );
}
