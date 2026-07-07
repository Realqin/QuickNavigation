import { Alert, Form, Input, Modal, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { fetchRepoAccessSettings, updateRepoAccessSettings } from '../api';
import type { RepoAccessSettings } from '../types';
import { showApiError } from '../utils/apiError';

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

interface FormValues {
  gitlab_base_url: string;
  public_webhook_base_url: string;
  gitlab_token?: string;
  gitlab_ssh_private_key?: string;
  github_token?: string;
}

export default function RepoAccessSettingsModal({ open, onClose, onSaved }: Props) {
  const [form] = Form.useForm<FormValues>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [current, setCurrent] = useState<RepoAccessSettings | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    fetchRepoAccessSettings()
      .then((data) => {
        setCurrent(data);
        form.setFieldsValue({
          gitlab_base_url: data.gitlab_base_url,
          public_webhook_base_url: data.public_webhook_base_url,
          gitlab_token: undefined,
          github_token: undefined,
        });
      })
      .catch((error) => showApiError(error, '加载配置失败'))
      .finally(() => setLoading(false));
  }, [open, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const payload: Parameters<typeof updateRepoAccessSettings>[0] = {
        gitlab_base_url: values.gitlab_base_url.trim(),
        public_webhook_base_url: values.public_webhook_base_url.trim(),
      };
      if (values.gitlab_token?.trim()) {
        payload.gitlab_token = values.gitlab_token.trim();
      }
      if (values.gitlab_ssh_private_key?.trim()) {
        payload.gitlab_ssh_private_key = values.gitlab_ssh_private_key.trim();
      }
      if (values.github_token?.trim()) {
        payload.github_token = values.github_token.trim();
      }
      await updateRepoAccessSettings(payload);
      message.success('配置已保存');
      onSaved?.();
      onClose();
    } catch (error) {
      showApiError(error, '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="仓库访问配置"
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      confirmLoading={saving}
      okText="保存"
      cancelText="取消"
      width={560}
      destroyOnHidden
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="用于拉取私有仓库 commit diff，以及复制 Webhook 对外地址。若 GitLab HTTP 不可用，可配置 SSH Deploy Key。"
      />
      <Form form={form} layout="vertical" disabled={loading}>
        <Form.Item
          name="gitlab_base_url"
          label="GitLab 地址"
          rules={[{ required: true, message: '请输入 GitLab 根地址' }]}
          extra="示例：http://gitlab.bj.uniseas.com.cn（不要带项目路径）"
        >
          <Input placeholder="http://gitlab.example.com" />
        </Form.Item>
        <Form.Item
          name="gitlab_token"
          label="GitLab Token"
          extra={
            current?.gitlab_token_set ? (
              <Typography.Text type="secondary">
                已配置 {current.gitlab_token_hint}，留空则保持不变
              </Typography.Text>
            ) : (
              'GitLab → 偏好设置 → Access Tokens，勾选 read_api'
            )
          }
        >
          <Input.Password placeholder="输入新的 GitLab Token" autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="gitlab_ssh_private_key"
          label="GitLab SSH 私钥（Deploy Key）"
          extra={
            current?.gitlab_ssh_key_set ? (
              <Typography.Text type="secondary">
                已配置 SSH 私钥，留空则保持不变；填写新内容将覆盖
              </Typography.Text>
            ) : (
              '在 GitLab 项目 Settings → Repository → Deploy keys 添加公钥后，粘贴对应私钥（含 BEGIN/END 行）'
            )
          }
        >
          <Input.TextArea
            rows={4}
            placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
            autoComplete="new-password"
          />
        </Form.Item>
        <Form.Item
          name="github_token"
          label="GitHub Token"
          extra={
            current?.github_token_set ? (
              <Typography.Text type="secondary">
                已配置 {current.github_token_hint}，留空则保持不变
              </Typography.Text>
            ) : (
              'GitHub → Settings → Developer settings → Personal access tokens'
            )
          }
        >
          <Input.Password placeholder="输入新的 GitHub Token" autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="public_webhook_base_url"
          label="Webhook 对外基址"
          extra="GitLab 服务器能访问的地址，用于复制 Webhook URL"
        >
          <Input placeholder="http://192.168.6.127:8000" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
