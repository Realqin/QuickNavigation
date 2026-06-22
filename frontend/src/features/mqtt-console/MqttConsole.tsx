import { CloseOutlined, ClearOutlined, EditOutlined, PlusOutlined, SendOutlined } from '@ant-design/icons';
import {
  App,
  Button,
  Card,
  Col,
  Input,
  Modal,
  Row,
  Space,
  Tag,
  Typography,
} from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { MqttSubscription } from '../../types';
import type { MqttConnectionForm } from './types';
import { buildMqttWebSocketUrl } from './buildWebSocketUrl';
import { formatMessagePayload } from './formatMessagePayload';
import MqttMessageVirtualList from './MqttMessageVirtualList';
import { MQTT_CONNECTION_MAX_MS } from './mqttConsoleLimits';
import { useMqttMessageBuffer } from './useMqttMessageBuffer';
import { nextMessageColorIndex } from './messageColors';
import { mqttTopicMatches } from './mqttTopicMatch';

import { useMqttBridgeClient } from './useMqttBridgeClient';
import { useMqttManualBridgeClient } from './useMqttManualBridgeClient';
import { useMqttClient } from './useMqttClient';
import './mqtt-console.css';

interface Props {
  initialConnection?: Partial<MqttConnectionForm>;
  presetSubscriptions?: MqttSubscription[];
  connectionName?: string;
  autoConnect?: boolean;
  /** 从导航进入时使用后端 TCP 代理（与 MQTTX mqtt:// 一致） */
  bridgeConnectionId?: number;
  /** 连接方式页：手动填写 mqtt://host:1883，经后端 TCP 桥接 */
  manualBridge?: boolean;
  /** 由侧栏管理连接时隐藏控制台内的连接配置卡片 */
  hideConnectionPanel?: boolean;
  /** 由侧栏管理订阅时隐藏控制台内的订阅卡片 */
  hideSubscriptionPanel?: boolean;
  /** 侧栏受控选中 Topic，用于过滤消息流 */
  selectedTopic?: string | null;
  onSelectedTopicChange?: (topic: string | null) => void;
  /** 由父组件控制 Broker 连接状态；断开时保留消息列表 */
  brokerActive?: boolean;
}

const defaultForm: MqttConnectionForm = {
  host: '',
  port: 1883,
  wsPath: '/mqtt',
  username: '',
  password: '',
  clientId: '',
};

function formatPayload(payload: Buffer): string {
  try {
    return payload.toString('utf8');
  } catch {
    return payload.toString('hex');
  }
}

export default function MqttConsole({
  initialConnection,
  presetSubscriptions = [],
  connectionName,
  autoConnect = false,
  bridgeConnectionId,
  manualBridge = false,
  hideConnectionPanel = false,
  hideSubscriptionPanel = false,
  selectedTopic: controlledSelectedTopic,
  onSelectedTopicChange,
  brokerActive,
}: Props) {
  const { message } = App.useApp();
  const useSavedBridge = Boolean(bridgeConnectionId && bridgeConnectionId > 0);
  const useManualBridge = manualBridge && !useSavedBridge;
  const useBridge = useSavedBridge || useManualBridge;
  const isTopicControlled = onSelectedTopicChange !== undefined;
  const brokerActiveControlled = brokerActive !== undefined;
  const messagesOnly = hideConnectionPanel && hideSubscriptionPanel;
  const [form, setForm] = useState<MqttConnectionForm>({ ...defaultForm, ...initialConnection });
  const [newTopic, setNewTopic] = useState('');
  const [publishPayload, setPublishPayload] = useState('');
  const [filterText, setFilterText] = useState('');
  const [internalSelectedTopic, setInternalSelectedTopic] = useState<string | null>(null);
  const selectedTopic = isTopicControlled ? (controlledSelectedTopic ?? null) : internalSelectedTopic;
  const setSelectedTopic = (topic: string | null) => {
    if (isTopicControlled) {
      onSelectedTopicChange?.(topic);
      return;
    }
    setInternalSelectedTopic(topic);
  };
  const [showAddSubscription, setShowAddSubscription] = useState(false);
  const [editingTopic, setEditingTopic] = useState<string | null>(null);
  const [editTopicValue, setEditTopicValue] = useState('');
  const [displayTopics, setDisplayTopics] = useState<string[]>([]);
  const { messages, pushMessage: pushBufferedMessage, clearMessages } = useMqttMessageBuffer();
  const messageSeqRef = useRef(0);
  const directClient = useMqttClient();
  const bridgeClient = useMqttBridgeClient();
  const manualBridgeClient = useMqttManualBridgeClient();
  const autoConnectAttemptedRef = useRef(false);
  const prevStatusRef = useRef<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
  const messageColorRef = useRef(-1);
  const connectionTimerRef = useRef<number | null>(null);
  const bridgeConnectRef = useRef(bridgeClient.connect);
  const directConnectRef = useRef(directClient.connect);
  const manualBridgeConnectRef = useRef(manualBridgeClient.connect);
  bridgeConnectRef.current = bridgeClient.connect;
  directConnectRef.current = directClient.connect;
  manualBridgeConnectRef.current = manualBridgeClient.connect;

  const activeBridgeClient = useManualBridge ? manualBridgeClient : bridgeClient;
  const status = useBridge ? activeBridgeClient.status : directClient.status;
  const error = useBridge ? activeBridgeClient.error : directClient.error;
  const activeTopics = useBridge ? activeBridgeClient.activeTopics : directClient.activeTopics;
  const subscribe = useBridge ? activeBridgeClient.subscribe : directClient.subscribe;
  const unsubscribe = useBridge ? activeBridgeClient.unsubscribe : directClient.unsubscribe;
  const publish = useBridge ? activeBridgeClient.publish : directClient.publish;
  const disconnect = useBridge ? activeBridgeClient.disconnect : directClient.disconnect;

  const presetTopics = useMemo(
    () => presetSubscriptions.map((item) => item.topic).filter(Boolean),
    [presetSubscriptions],
  );

  useEffect(() => {
    if (presetTopics.length === 0) {
      return;
    }
    setDisplayTopics((prev) => {
      const merged = new Set([...presetTopics, ...prev]);
      return Array.from(merged);
    });
  }, [presetTopics]);

  useEffect(() => {
    if (status !== 'connected' || activeTopics.length === 0) {
      return;
    }
    setDisplayTopics((prev) => {
      const merged = new Set([...prev, ...activeTopics]);
      return Array.from(merged);
    });
  }, [status, activeTopics]);

  useEffect(() => {
    if (status !== 'connected') {
      return;
    }
    const pending = displayTopics.filter((topic) => !activeTopics.includes(topic));
    if (pending.length === 0) {
      return;
    }
    pending.forEach((topic) => {
      subscribe(topic).catch(() => undefined);
    });
  }, [status, displayTopics, activeTopics, subscribe]);

  const subscriptionItems = useMemo(() => {
    const nameByTopic = new Map(
      presetSubscriptions.map((item) => [item.topic, item.name || item.topic]),
    );
    return displayTopics.map((topic) => ({
      topic,
      name: nameByTopic.get(topic) ?? topic,
    }));
  }, [displayTopics, presetSubscriptions]);

  const brokerUrlPreview = useMemo(() => {
    if (useBridge) {
      const broker =
        activeBridgeClient.bridgeTarget ??
        (form.host.trim() ? `mqtt://${form.host.trim()}:${form.port || 1883}` : 'mqtt://');
      const channel = activeBridgeClient.bridgeChannel ?? 'ws://本机后端/ws/mqtt/...';
      return `Broker ${broker} · 代理通道 ${channel}`;
    }
    return buildMqttWebSocketUrl(form.host.trim(), form.port, form.wsPath.trim() || '/mqtt');
  }, [
    useBridge,
    activeBridgeClient.bridgeTarget,
    activeBridgeClient.bridgeChannel,
    form.host,
    form.port,
    form.wsPath,
  ]);

  const pushMessage = (topic: string, payload: string) => {
    const receivedAtMs = Date.now();
    messageColorRef.current = nextMessageColorIndex(messageColorRef.current);
    messageSeqRef.current += 1;
    pushBufferedMessage({
      id: `m${messageSeqRef.current}`,
      topic,
      payload: formatMessagePayload(payload),
      receivedAt: new Date(receivedAtMs).toLocaleString(),
      receivedAtMs,
      colorIndex: messageColorRef.current,
    });
  };

  useEffect(() => {
    if (initialConnection) {
      setForm((prev) => ({ ...defaultForm, ...prev, ...initialConnection }));
    }
  }, [initialConnection]);

  useEffect(() => {
    if (brokerActiveControlled || !autoConnect || autoConnectAttemptedRef.current) {
      return;
    }
    if (useBridge && bridgeConnectionId) {
      autoConnectAttemptedRef.current = true;
      bridgeConnectRef
        .current(bridgeConnectionId)
        .then(() => message.success('MQTT 已连接'))
        .catch((err) => {
          autoConnectAttemptedRef.current = false;
          message.error(err instanceof Error ? err.message : '连接失败');
        });
      return;
    }
    if (useManualBridge && initialConnection?.host?.trim()) {
      autoConnectAttemptedRef.current = true;
      const connectionForm = { ...defaultForm, ...initialConnection };
      manualBridgeConnectRef
        .current(connectionForm)
        .then(() => message.success('MQTT 已连接'))
        .catch((err) => {
          autoConnectAttemptedRef.current = false;
          message.error(err instanceof Error ? err.message : '连接失败');
        });
      return;
    }
    if (!initialConnection?.host?.trim()) {
      return;
    }
    autoConnectAttemptedRef.current = true;
    const connectionForm = { ...defaultForm, ...initialConnection };
    directConnectRef
      .current(connectionForm, displayTopics.length > 0 ? displayTopics : presetTopics)
      .then(() => message.success('MQTT 已连接'))
      .catch((err) => message.error(err instanceof Error ? err.message : '连接失败'));
  }, [
    autoConnect,
    brokerActiveControlled,
    useBridge,
    useManualBridge,
    bridgeConnectionId,
    initialConnection,
    presetTopics,
    displayTopics,
    message,
  ]);

  useEffect(() => {
    if (!brokerActiveControlled) {
      return;
    }

    if (!brokerActive) {
      if (status === 'connected' || status === 'connecting') {
        disconnect();
      }
      return;
    }

    if (status === 'connected' || status === 'connecting') {
      return;
    }

    const runConnect = async () => {
      try {
        if (useManualBridge) {
          const connectionForm = { ...defaultForm, ...initialConnection, ...form };
          if (!connectionForm.host.trim()) {
            return;
          }
          await manualBridgeConnectRef.current(connectionForm);
          message.success('MQTT 已连接');
          return;
        }
        if (useSavedBridge && bridgeConnectionId) {
          await bridgeConnectRef.current(bridgeConnectionId);
          message.success('MQTT 已连接');
        }
      } catch (err) {
        message.error(err instanceof Error ? err.message : '连接失败');
      }
    };

    void runConnect();
  }, [
    brokerActive,
    brokerActiveControlled,
    bridgeConnectionId,
    disconnect,
    message,
    status,
    useManualBridge,
    useSavedBridge,
  ]);

  useEffect(() => {
    if (status !== 'connected') {
      return;
    }
    if (useBridge) {
      return activeBridgeClient.bindMessageHandler((topic, payload) =>
        pushMessage(topic, payload),
      );
    }
    return directClient.bindMessageHandler((topic, payload) =>
      pushMessage(topic, formatPayload(payload)),
    );
  }, [status, useBridge, activeBridgeClient, directClient]);

  useEffect(() => {
    if (status !== 'connected') {
      if (connectionTimerRef.current) {
        window.clearTimeout(connectionTimerRef.current);
        connectionTimerRef.current = null;
      }
      return;
    }

    connectionTimerRef.current = window.setTimeout(() => {
      disconnect();
      message.warning('连接已超过 30 分钟，已自动断开');
    }, MQTT_CONNECTION_MAX_MS);

    return () => {
      if (connectionTimerRef.current) {
        window.clearTimeout(connectionTimerRef.current);
        connectionTimerRef.current = null;
      }
    };
  }, [status, disconnect, message]);

  const disconnectRef = useRef(disconnect);
  disconnectRef.current = disconnect;

  useEffect(() => {
    const handleUnload = () => {
      disconnectRef.current();
    };
    window.addEventListener('pagehide', handleUnload);
    window.addEventListener('beforeunload', handleUnload);
    return () => {
      window.removeEventListener('pagehide', handleUnload);
      window.removeEventListener('beforeunload', handleUnload);
      disconnectRef.current();
    };
  }, []);

  const filteredMessages = useMemo(() => {
    let result = messages;
    if (selectedTopic) {
      result = result.filter((item) => mqttTopicMatches(selectedTopic, item.topic));
    }
    const keyword = filterText.trim().toLowerCase();
    if (keyword) {
      result = result.filter(
        (item) =>
          item.topic.toLowerCase().includes(keyword) ||
          item.payload.toLowerCase().includes(keyword),
      );
    }
    return [...result].sort((a, b) => a.receivedAtMs - b.receivedAtMs);
  }, [messages, selectedTopic, filterText]);

  useEffect(() => {
    const justConnected = status === 'connected' && prevStatusRef.current !== 'connected';
    prevStatusRef.current = status;

    if (displayTopics.length === 0) {
      setSelectedTopic(null);
      return;
    }

    if (justConnected) {
      setSelectedTopic((prev) => {
        if (prev && displayTopics.includes(prev)) {
          return prev;
        }
        return displayTopics[0];
      });
      return;
    }

    if (selectedTopic && !displayTopics.includes(selectedTopic)) {
      setSelectedTopic(displayTopics[0]);
    }
  }, [status, displayTopics, selectedTopic]);

  const updateForm = (patch: Partial<MqttConnectionForm>) => {
    setForm((prev) => ({ ...prev, ...patch }));
  };

  const handleConnect = async () => {
    if (useManualBridge) {
      try {
        await manualBridgeClient.connect(form);
        message.success('MQTT 已连接');
      } catch (err) {
        message.error(err instanceof Error ? err.message : '连接失败');
      }
      return;
    }
    if (useSavedBridge && bridgeConnectionId) {
      try {
        await bridgeClient.connect(bridgeConnectionId);
        message.success('MQTT 已连接');
      } catch (err) {
        message.error(err instanceof Error ? err.message : '连接失败');
      }
      return;
    }
    if (!form.host.trim()) {
      message.warning('请输入主机');
      return;
    }
    try {
      await directClient.connect(
        form,
        displayTopics.length > 0 ? displayTopics : presetTopics,
      );
      message.success('MQTT 已连接');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '连接失败');
    }
  };

  const handleDisconnect = () => {
    disconnect();
    message.info('已断开连接');
  };

  const handleSelectSubscription = (topic: string) => {
    setSelectedTopic(topic);
  };

  const handleAddSubscription = async () => {
    const topic = newTopic.trim();
    if (!topic) {
      message.warning('请输入 Topic');
      return;
    }
    if (displayTopics.includes(topic)) {
      message.warning('该 Topic 已在列表中');
      return;
    }
    try {
      if (status === 'connected') {
        await subscribe(topic);
      }
      setDisplayTopics((prev) => [...prev, topic]);
      setSelectedTopic(topic);
      setNewTopic('');
      message.success(status === 'connected' ? `已订阅 ${topic}` : `已添加 ${topic}（连接后自动订阅）`);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '订阅失败');
    }
  };

  const handleOpenEditSubscription = (topic: string) => {
    setEditingTopic(topic);
    setEditTopicValue(topic);
  };

  const handleSaveEditSubscription = async () => {
    const oldTopic = editingTopic;
    if (!oldTopic) {
      return;
    }
    const newTopic = editTopicValue.trim();
    if (!newTopic) {
      message.warning('请输入 Topic');
      return;
    }
    if (newTopic === oldTopic) {
      setEditingTopic(null);
      return;
    }
    if (displayTopics.includes(newTopic)) {
      message.warning('该 Topic 已存在');
      return;
    }
    try {
      if (status === 'connected') {
        await unsubscribe(oldTopic);
        await subscribe(newTopic);
      }
      setDisplayTopics((prev) => prev.map((item) => (item === oldTopic ? newTopic : item)));
      if (selectedTopic === oldTopic) {
        setSelectedTopic(newTopic);
      }
      setEditingTopic(null);
      message.success('订阅已更新');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '更新订阅失败');
    }
  };

  const handleRemoveSubscription = async (topic: string) => {
    try {
      if (status === 'connected') {
        await unsubscribe(topic);
      }
      setDisplayTopics((prev) => prev.filter((item) => item !== topic));
      if (selectedTopic === topic) {
        const remaining = displayTopics.filter((item) => item !== topic);
        setSelectedTopic(remaining[0] ?? null);
      }
      message.success(`已移除 ${topic}`);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '取消订阅失败');
    }
  };

  const handleClearMessages = () => {
    messageSeqRef.current = 0;
    clearMessages();
    messageColorRef.current = -1;
    message.success('消息已清空');
  };

  const handlePublish = async () => {
    const topic = selectedTopic?.trim();
    if (!topic) {
      message.warning('请先选择要发送的订阅 Topic');
      return;
    }
    if (!publishPayload.trim()) {
      message.warning('请输入消息内容');
      return;
    }
    try {
      await publish(topic, publishPayload);
      setPublishPayload('');
      message.success('消息已发送');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '发送失败');
    }
  };

  const statusColor =
    status === 'connected'
      ? 'success'
      : status === 'connecting'
        ? 'processing'
        : status === 'error'
          ? 'error'
          : 'default';

  return (
    <div className="mqtt-console">
      <div className="mqtt-console__header">
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            MQTT 控制台
          </Typography.Title>
          {connectionName ? (
            <Typography.Text type="secondary">{connectionName}</Typography.Text>
          ) : null}
        </div>
        <Tag color={statusColor}>{status}</Tag>
      </div>

      <Row gutter={[16, 16]} className="mqtt-console__main-row">
        {!messagesOnly ? (
        <Col xs={24} lg={7} className="mqtt-console__left-col">
          {!hideConnectionPanel ? (
          <Card title="连接配置" size="small" className="mqtt-console__card">
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Input
                addonBefore="主机"
                value={form.host}
                onChange={(e) => updateForm({ host: e.target.value })}
                placeholder="10.100.0.230"
                readOnly={useSavedBridge}
              />
              {useBridge ? (
                <Input
                  addonBefore="TCP 端口"
                  value={String(form.port)}
                  onChange={
                    useManualBridge
                      ? (e) => updateForm({ port: Number(e.target.value) || 1883 })
                      : undefined
                  }
                  readOnly={useSavedBridge}
                />
              ) : (
                <Space.Compact style={{ width: '100%' }}>
                  <Input
                    addonBefore="WS 端口"
                    value={String(form.port)}
                    onChange={(e) => updateForm({ port: Number(e.target.value) || 8083 })}
                    style={{ width: '50%' }}
                  />
                  <Input
                    addonBefore="路径"
                    value={form.wsPath}
                    onChange={(e) => updateForm({ wsPath: e.target.value })}
                    placeholder="/mqtt"
                    style={{ width: '50%' }}
                  />
                </Space.Compact>
              )}
              {useManualBridge || !useBridge ? (
                <>
                  <Input
                    addonBefore="用户名"
                    value={form.username}
                    onChange={(e) => updateForm({ username: e.target.value })}
                    placeholder="可选"
                  />
                  <Input.Password
                    addonBefore="密码"
                    value={form.password}
                    onChange={(e) => updateForm({ password: e.target.value })}
                    placeholder="可选"
                  />
                  {!useBridge ? (
                    <Input
                      addonBefore="Client ID"
                      value={form.clientId}
                      onChange={(e) => updateForm({ clientId: e.target.value })}
                      placeholder="留空自动生成"
                    />
                  ) : null}
                </>
              ) : (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  账号密码使用连接配置中已保存的值，由后端代为连接 Broker
                </Typography.Text>
              )}
              <Space>
                <Button
                  type={status === 'connected' ? 'default' : 'primary'}
                  onClick={handleConnect}
                  loading={status === 'connecting'}
                  disabled={status === 'connected' || status === 'connecting'}
                >
                  连接
                </Button>
                <Button
                  type={status === 'connected' ? 'primary' : 'default'}
                  onClick={handleDisconnect}
                  disabled={status !== 'connected'}
                >
                  停止
                </Button>
              </Space>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                连接方式：{brokerUrlPreview}
              </Typography.Text>
              {error ? <Typography.Text type="danger">{error}</Typography.Text> : null}
            </Space>
          </Card>
          ) : null}

          {!hideSubscriptionPanel ? (
          <Card title="订阅管理" size="small" className="mqtt-console__card mqtt-console__subscription-panel">
            <button
              type="button"
              className="mqtt-console__new-subscription"
              onClick={() => setShowAddSubscription((prev) => !prev)}
            >
              <PlusOutlined />
              <span>新建订阅</span>
            </button>
            {showAddSubscription ? (
              <Space.Compact className="mqtt-console__add-subscription">
                <Input
                  value={newTopic}
                  onChange={(e) => setNewTopic(e.target.value)}
                  placeholder="Topic，如 cctv/#"
                  onPressEnter={() => handleAddSubscription()}
                />
                <Button type="primary" onClick={handleAddSubscription}>
                  订阅
                </Button>
              </Space.Compact>
            ) : null}
            {subscriptionItems.length === 0 ? (
              <Typography.Text type="secondary" className="mqtt-console__subscription-empty">
                暂无订阅
              </Typography.Text>
            ) : (
              <div className="mqtt-console__subscription-list">
                {subscriptionItems.map((item) => {
                  const isActive =
                    status === 'connected' && selectedTopic === item.topic;
                  return (
                    <div
                      key={item.topic}
                      className={`mqtt-console__subscription-card${isActive ? ' is-active' : ''}`}
                      onClick={() => handleSelectSubscription(item.topic)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          handleSelectSubscription(item.topic);
                        }
                      }}
                    >
                      <span className="mqtt-console__subscription-accent" />
                      <span className="mqtt-console__subscription-topic">{item.topic}</span>
                      <div className="mqtt-console__subscription-actions">
                        <button
                          type="button"
                          className="mqtt-console__subscription-action"
                          title="编辑订阅"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenEditSubscription(item.topic);
                          }}
                        >
                          <EditOutlined />
                        </button>
                        <button
                          type="button"
                          className="mqtt-console__subscription-action mqtt-console__subscription-action--danger"
                          title="取消订阅"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRemoveSubscription(item.topic);
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
          </Card>
          ) : null}
        </Col>
        ) : null}

        <Col xs={24} lg={messagesOnly ? 24 : 17} className="mqtt-console__right-col">
          <Card
            title={
              selectedTopic
                ? `消息流 · ${selectedTopic}`
                : '消息流'
            }
            size="small"
            className="mqtt-console__card mqtt-console__messages-card"
            extra={
              <Space size={8}>
                <Button
                  size="small"
                  icon={<ClearOutlined />}
                  onClick={handleClearMessages}
                  disabled={messages.length === 0}
                >
                  清空
                </Button>
                <Input
                  allowClear
                  placeholder="过滤 Topic / 内容"
                  value={filterText}
                  onChange={(e) => setFilterText(e.target.value)}
                  style={{ width: 220 }}
                />
              </Space>
            }
          >
            <div className="mqtt-console__message-column">
              <MqttMessageVirtualList
                messages={filteredMessages}
                selectedTopic={selectedTopic}
              />
              <div className="mqtt-console__publish-box">
                <Input.TextArea
                  className="mqtt-console__publish-input"
                  value={publishPayload}
                  onChange={(e) => setPublishPayload(e.target.value)}
                  placeholder={
                    selectedTopic
                      ? `发送到 ${selectedTopic}`
                      : '输入消息内容（发送前请选择订阅 Topic）'
                  }
                  rows={4}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                      e.preventDefault();
                      handlePublish();
                    }
                  }}
                />
                <div className="mqtt-console__publish-actions">
                  <Button type="primary" icon={<SendOutlined />} onClick={handlePublish}>
                    发送
                  </Button>
                </div>
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      <Modal
        title="编辑订阅"
        open={editingTopic !== null}
        onOk={() => handleSaveEditSubscription()}
        onCancel={() => setEditingTopic(null)}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Input
          value={editTopicValue}
          onChange={(e) => setEditTopicValue(e.target.value)}
          placeholder="Topic，如 cctv/#"
          onPressEnter={() => handleSaveEditSubscription()}
        />
      </Modal>
    </div>
  );
}
