import { CloseOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import { App, Button, Input, Modal, Typography } from 'antd';
import { useEffect, useState } from 'react';
import type { MqttSubscription } from '../types';
import '../features/mqtt-console/mqtt-console.css';

interface Props {
  connectionName?: string | null;
  subscriptions: MqttSubscription[];
  selectedTopic: string | null;
  disabled?: boolean;
  muted?: boolean;
  saving?: boolean;
  onSelectTopic: (topic: string | null) => void;
  onChange: (subscriptions: MqttSubscription[]) => Promise<void>;
}

export default function MqttMethodSubscriptionPanel({
  connectionName,
  subscriptions,
  selectedTopic,
  disabled = false,
  muted = false,
  saving = false,
  onSelectTopic,
  onChange,
}: Props) {
  const { message } = App.useApp();
  const [showAdd, setShowAdd] = useState(false);
  const [newTopic, setNewTopic] = useState('');
  const [editingTopic, setEditingTopic] = useState<string | null>(null);
  const [editTopicValue, setEditTopicValue] = useState('');

  useEffect(() => {
    setShowAdd(false);
    setNewTopic('');
    setEditingTopic(null);
  }, [connectionName]);

  const persist = async (next: MqttSubscription[]) => {
    try {
      await onChange(next);
    } catch {
      message.error('保存订阅失败');
    }
  };

  const handleAdd = async () => {
    const topic = newTopic.trim();
    if (!topic) {
      message.warning('请输入 Topic');
      return;
    }
    if (subscriptions.some((item) => item.topic === topic)) {
      message.warning('该 Topic 已存在');
      return;
    }
    await persist([...subscriptions, { topic, name: topic }]);
    setNewTopic('');
    setShowAdd(false);
    onSelectTopic(topic);
    message.success('订阅已保存');
  };

  const handleRemove = async (topic: string) => {
    const next = subscriptions.filter((item) => item.topic !== topic);
    await persist(next);
    if (selectedTopic === topic) {
      onSelectTopic(next[0]?.topic ?? null);
    }
    message.success('已删除订阅');
  };

  const handleOpenEdit = (item: MqttSubscription) => {
    setEditingTopic(item.topic);
    setEditTopicValue(item.topic);
  };

  const handleSaveEdit = async () => {
    const oldTopic = editingTopic;
    if (!oldTopic) {
      return;
    }
    const topic = editTopicValue.trim();
    if (!topic) {
      message.warning('请输入 Topic');
      return;
    }
    if (topic !== oldTopic && subscriptions.some((item) => item.topic === topic)) {
      message.warning('该 Topic 已存在');
      return;
    }
    const next = subscriptions.map((item) =>
      item.topic === oldTopic ? { topic, name: topic } : item,
    );
    await persist(next);
    if (selectedTopic === oldTopic) {
      onSelectTopic(topic);
    }
    setEditingTopic(null);
    message.success('订阅已更新');
  };

  return (
    <div
      className={`mqtt-method-page__subscriptions-panel${muted ? ' is-muted' : ''}${disabled ? ' is-disabled' : ''}`}
    >
      <div className="mqtt-method-page__subscriptions-head">
        <Typography.Text strong>订阅管理</Typography.Text>
        {connectionName ? (
          <Typography.Text type="secondary" className="mqtt-method-page__subscriptions-subtitle">
            {connectionName}
          </Typography.Text>
        ) : null}
      </div>

      <div className="mqtt-method-page__subscriptions-scroll">
        {showAdd ? (
          <div className="mqtt-method-page__subscription-add">
            <Input
              value={newTopic}
              onChange={(e) => setNewTopic(e.target.value)}
              placeholder="Topic，如 cctv/#"
              disabled={disabled || saving}
              onPressEnter={() => handleAdd()}
            />
            <Button
              disabled={disabled || saving}
              onClick={() => {
                setShowAdd(false);
                setNewTopic('');
              }}
            >
              取消
            </Button>
            <Button type="primary" onClick={handleAdd} loading={saving} disabled={disabled}>
              保存
            </Button>
          </div>
        ) : (
          <button
            type="button"
            className="mqtt-console__new-subscription"
            disabled={disabled || saving}
            onClick={() => setShowAdd(true)}
          >
            <PlusOutlined />
            <span>新建订阅</span>
          </button>
        )}

        {disabled ? (
          <Typography.Text type="secondary" className="mqtt-console__subscription-empty">
            请先选择 MQTT 连接
          </Typography.Text>
        ) : subscriptions.length === 0 ? (
          <Typography.Text type="secondary" className="mqtt-console__subscription-empty">
            暂无订阅，点击上方新建
          </Typography.Text>
        ) : (
          <div className="mqtt-console__subscription-list">
            {subscriptions.map((item) => {
              const isActive = selectedTopic === item.topic;
              return (
                <div
                  key={item.topic}
                  className={`mqtt-console__subscription-card${isActive ? ' is-active' : ''}`}
                  onClick={() => onSelectTopic(item.topic)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      onSelectTopic(item.topic);
                    }
                  }}
                >
                  <span className="mqtt-console__subscription-accent" />
                  <div className="mqtt-method-page__subscription-text">
                    <span className="mqtt-console__subscription-topic">{item.topic}</span>
                    {item.name && item.name !== item.topic ? (
                      <span className="mqtt-method-page__subscription-name">{item.name}</span>
                    ) : null}
                  </div>
                  <div className="mqtt-console__subscription-actions">
                    <button
                      type="button"
                      className="mqtt-console__subscription-action"
                      title="编辑订阅"
                      disabled={saving}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleOpenEdit(item);
                      }}
                    >
                      <EditOutlined />
                    </button>
                    <button
                      type="button"
                      className="mqtt-console__subscription-action mqtt-console__subscription-action--danger"
                      title="删除订阅"
                      disabled={saving}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRemove(item.topic);
                      }}
                    >
                      <CloseOutlined />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <Modal
        title="编辑订阅"
        open={editingTopic !== null}
        onOk={handleSaveEdit}
        onCancel={() => setEditingTopic(null)}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        destroyOnHidden
      >
        <Input
          value={editTopicValue}
          onChange={(e) => setEditTopicValue(e.target.value)}
          placeholder="Topic，如 cctv/#"
          onPressEnter={handleSaveEdit}
        />
      </Modal>
    </div>
  );
}
