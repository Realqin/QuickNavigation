import {
  ApiOutlined,
  DisconnectOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { App, Button, Empty, Space, Spin, Tree, Typography } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  connectMqttConsole,
  createMqttConsoleConnection,
  deleteMqttConsoleConnection,
  fetchMqttConsoleConnections,
  updateMqttConsoleConnection,
  updateMqttConsoleSubscriptions,
} from '../../api';
import MqttConsoleConnectionModal from '../../components/MqttConsoleConnectionModal';
import MqttMethodSubscriptionPanel from '../../components/MqttMethodSubscriptionPanel';
import MqttConsole from '../../features/mqtt-console/MqttConsole';
import { registerPageCleanup } from '../../utils/pageCleanup';
import { showApiError } from '../../utils/apiError';
import type {
  MqttConsoleConnectResult,
  MqttConsoleConnection,
  MqttConsoleConnectionFormValues,
  MqttSubscription,
} from '../../types';

export default function ConnectionMethodMqttPage() {
  const { message, modal } = App.useApp();

  const [connections, setConnections] = useState<MqttConsoleConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [savingSubscriptions, setSavingSubscriptions] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [connectedId, setConnectedId] = useState<number | null>(null);
  const [consoleSession, setConsoleSession] = useState<MqttConsoleConnectResult | null>(null);
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<MqttConsoleConnection | null>(null);
  const connectedRef = useRef(false);

  const selectedConnection = useMemo(
    () => connections.find((item) => item.id === selectedId) ?? null,
    [connections, selectedId],
  );

  const selectedSubscriptions = useMemo(
    () => selectedConnection?.mqtt_subscriptions ?? [],
    [selectedConnection],
  );

  const loadConnections = useCallback(async () => {
    setLoading(true);
    try {
      const list = await fetchMqttConsoleConnections();
      setConnections(list);
      setSelectedId((prev) => {
        if (prev != null && list.some((item) => item.id === prev)) {
          return prev;
        }
        return null;
      });
      setConnectedId((prev) => {
        if (prev != null && list.some((item) => item.id === prev)) {
          return prev;
        }
        setConsoleSession(null);
        return null;
      });
    } catch (error) {
      showApiError(error, '加载 MQTT 连接失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  const handleEdit = useCallback((conn: MqttConsoleConnection) => {
    setEditing(conn);
    setModalOpen(true);
  }, []);

  const handleDelete = useCallback(
    (conn: MqttConsoleConnection) => {
      modal.confirm({
        title: '删除 MQTT 连接',
        content: `确定删除「${conn.name}」？此操作不可恢复。`,
        okText: '删除',
        okType: 'danger',
        cancelText: '取消',
        onOk: async () => {
          setDeletingId(conn.id);
          try {
            if (connectedId === conn.id) {
              setConnectedId(null);
            }
            if (consoleSession?.connection_id === conn.id) {
              setConsoleSession(null);
            }
            await deleteMqttConsoleConnection(conn.id);
            message.success('删除成功');
            if (selectedId === conn.id) {
              setSelectedId(null);
              setSelectedTopic(null);
            }
            await loadConnections();
          } catch (error) {
            showApiError(error, '删除失败');
          } finally {
            setDeletingId(null);
          }
        },
      });
    },
    [connectedId, consoleSession, loadConnections, message, modal, selectedId],
  );

  const treeData = useMemo<DataNode[]>(
    () =>
      connections.map((conn) => ({
        key: String(conn.id),
        title: (
          <div className="mqtt-method-page__tree-node">
            <div className="mqtt-method-page__tree-main">
              <span className="mqtt-method-page__tree-name">{conn.name}</span>
              <span className="mqtt-method-page__tree-brokers">
                mqtt://{conn.host}:{conn.port}
              </span>
            </div>
            <div className="mqtt-method-page__tree-actions">
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                title="编辑"
                onClick={(event) => {
                  event.stopPropagation();
                  handleEdit(conn);
                }}
              />
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                title="删除"
                loading={deletingId === conn.id}
                onClick={(event) => {
                  event.stopPropagation();
                  handleDelete(conn);
                }}
              />
            </div>
          </div>
        ),
        isLeaf: true,
      })),
    [connections, deletingId, handleDelete, handleEdit],
  );

  useEffect(() => {
    loadConnections();
  }, [loadConnections]);

  connectedRef.current = connectedId != null;

  useEffect(() => {
    return registerPageCleanup(() => {
      if (connectedRef.current) {
        connectedRef.current = false;
        setConnectedId(null);
      }
    });
  }, []);

  useEffect(() => {
    if (!selectedConnection) {
      setSelectedTopic(null);
      return;
    }
    setSelectedTopic((prev) => {
      if (prev && selectedSubscriptions.some((item) => item.topic === prev)) {
        return prev;
      }
      return selectedSubscriptions[0]?.topic ?? null;
    });
  }, [selectedConnection, selectedSubscriptions]);

  const handleSubscriptionsChange = async (subscriptions: MqttSubscription[]) => {
    if (!selectedConnection) {
      return;
    }
    setSavingSubscriptions(true);
    try {
      const updated = await updateMqttConsoleSubscriptions(selectedConnection.id, subscriptions);
      setConnections((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item)),
      );
    } finally {
      setSavingSubscriptions(false);
    }
  };

  const handleDisconnect = () => {
    setConnectedId(null);
    message.info('已取消连接');
  };

  const handleConnect = async () => {
    if (!selectedConnection) {
      message.warning('请先在左侧选择一个 MQTT 连接');
      return;
    }
    const hide = message.loading('正在连接 MQTT Broker...', 0);
    setConnecting(true);
    try {
      const data = await connectMqttConsole(selectedConnection.id);
      setConsoleSession(data);
      setConnectedId(selectedConnection.id);
      message.success(`已连接：${selectedConnection.name}`);
    } catch (error) {
      showApiError(error, '连接 MQTT 失败，请确认 Broker 地址与后端服务可用');
    } finally {
      hide();
      setConnecting(false);
    }
  };

  const handleCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const handleSubmit = async (values: MqttConsoleConnectionFormValues) => {
    if (editing) {
      await updateMqttConsoleConnection(editing.id, values);
      message.success('更新成功');
    } else {
      await createMqttConsoleConnection(values);
      message.success('创建成功');
    }
    setModalOpen(false);
    setEditing(null);
    await loadConnections();
  };

  const isConnected = connectedId != null;

  const mqttInitialConnection = useMemo(
    () =>
      consoleSession
        ? {
            host: consoleSession.host,
            port: consoleSession.port,
            username: consoleSession.username,
            password: consoleSession.password,
          }
        : undefined,
    [consoleSession],
  );

  const mqttPresetSubscriptions = useMemo(
    () => consoleSession?.subscriptions ?? selectedSubscriptions,
    [consoleSession, selectedSubscriptions],
  );

  return (
    <div className="mqtt-method-page">
      <aside className="mqtt-method-page__sidebar">
        <div className="mqtt-method-page__sidebar-head">
          <Typography.Text strong>MQTT</Typography.Text>
          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => loadConnections()}
            loading={loading}
          />
        </div>

        <Space className="mqtt-method-page__toolbar" size={8} wrap>
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={handleCreate}>
            新增
          </Button>
          <Button
            size="small"
            type="primary"
            icon={<ApiOutlined />}
            onClick={handleConnect}
            loading={connecting}
            disabled={!selectedConnection || isConnected}
          >
            连接
          </Button>
          <Button
            size="small"
            icon={<DisconnectOutlined />}
            onClick={handleDisconnect}
            disabled={!isConnected}
          >
            取消连接
          </Button>
        </Space>

        <div className="mqtt-method-page__sidebar-body">
          <section className="mqtt-method-page__connections-panel">
            <div className="mqtt-method-page__panel-title">
              <Typography.Text strong>MQTT 连接</Typography.Text>
            </div>
            <div className="mqtt-method-page__connections-scroll">
              {loading ? (
                <div className="mqtt-method-page__tree-loading">
                  <Spin />
                </div>
              ) : treeData.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="暂无连接，点击新增创建"
                />
              ) : (
                <Tree
                  blockNode
                  showLine={false}
                  treeData={treeData}
                  defaultExpandAll
                  selectedKeys={selectedId != null ? [String(selectedId)] : []}
                  onSelect={(keys) => {
                    const raw = keys[0];
                    if (typeof raw !== 'string') {
                      return;
                    }
                    const nextId = Number(raw);
                    if (connectedId != null && connectedId !== nextId) {
                      setConnectedId(null);
                    }
                    if (consoleSession?.connection_id !== nextId) {
                      setConsoleSession(null);
                    }
                    setSelectedId(nextId);
                  }}
                />
              )}
            </div>
          </section>

          <MqttMethodSubscriptionPanel
            connectionName={selectedConnection?.name}
            subscriptions={selectedSubscriptions}
            selectedTopic={selectedTopic}
            disabled={!selectedConnection}
            saving={savingSubscriptions}
            onSelectTopic={setSelectedTopic}
            onChange={handleSubscriptionsChange}
          />
        </div>
      </aside>

      <section className="mqtt-method-page__main">
        {consoleSession ? (
          <MqttConsole
            key={consoleSession.connection_id}
            manualBridge
            brokerActive={isConnected}
            hideConnectionPanel
            hideSubscriptionPanel
            connectionName={consoleSession.connection_name}
            initialConnection={mqttInitialConnection}
            presetSubscriptions={mqttPresetSubscriptions}
            selectedTopic={selectedTopic}
            onSelectedTopicChange={setSelectedTopic}
          />
        ) : (
          <div className="mqtt-method-page__placeholder">
            <Empty description="请从左侧选择 MQTT 连接，再点击「连接」查看消息" />
          </div>
        )}
      </section>

      <MqttConsoleConnectionModal
        open={modalOpen}
        connection={editing}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onSubmit={handleSubmit}
      />
    </div>
  );
}

