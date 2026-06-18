import { Form, Input, Modal, Typography, message } from 'antd';
import { useEffect } from 'react';
import {
  type ApiMonitorEnvPreset,
  writeApiMonitorEnvPreset,
} from '../features/api-monitor/apiMonitorEnvPreset';

interface Props {
  open: boolean;
  preset: ApiMonitorEnvPreset;
  onClose: () => void;
  onSaved: (preset: ApiMonitorEnvPreset) => void;
}

interface FormValues {
  serverAddress: string;
  authorization: string;
}

export default function ApiMonitorEnvPresetModal({ open, preset, onClose, onSaved }: Props) {
  const [form] = Form.useForm<FormValues>();

  useEffect(() => {
    if (!open) {
      return;
    }
    form.setFieldsValue({
      serverAddress: preset.serverAddress,
      authorization: preset.authorization,
    });
  }, [form, open, preset]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const next: ApiMonitorEnvPreset = {
        serverAddress: values.serverAddress.trim(),
        authorization: values.authorization.trim(),
      };
      writeApiMonitorEnvPreset(next);
      message.success('环境预置已保存');
      onSaved(next);
      onClose();
    } catch {
      // validation errors
    }
  };

  return (
    <Modal
      title="环境预置"
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      okText="保存"
      cancelText="取消"
      width={520}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        调试时将自动使用此处配置的服务器地址与 Authorization，可在调试页手动修改请求地址。
      </Typography.Paragraph>
      <Form form={form} layout="vertical">
        <Form.Item
          name="serverAddress"
          label="服务器地址"
          rules={[{ required: true, message: '请输入服务器地址' }]}
        >
          <Input placeholder="http://host:port" />
        </Form.Item>
        <Form.Item
          name="authorization"
          label="Authorization"
          extra="可填写完整 Bearer Token，或仅填写 Token 内容"
        >
          <Input.Password placeholder="Bearer ***" autoComplete="off" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
