import {
  ApiOutlined,
  DisconnectOutlined,
  DeleteOutlined,
  EditOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { App, Button, Empty, Space, Spin, Tree, Typography } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  beaconDisconnectKafkaConsole,
  connectKafkaConsole,
  createKafkaConsoleConnection,
  deleteKafkaConsoleConnection,
  disconnectKafkaConsole,
  fetchKafkaConsoleConnections,
  updateKafkaConsoleConnection,
} from '../../api';
import KafkaConsoleConnectionModal from '../../components/KafkaConsoleConnectionModal';
import type { KafkaConsoleConnection, KafkaConsoleConnectionFormValues } from '../../types';
import { registerPageCleanup } from '../../utils/pageCleanup';
import { resolveRedpandaOpenUrl } from '../../utils/redpanda';
import { showApiError } from '../../utils/apiError';

export default function KafkaMethodPage() {
  const { message, modal } = App.useApp();

  const [connections, setConnections] = useState<KafkaConsoleConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [connectedId, setConnectedId] = useState<number | null>(null);
  const [consoleSrc, setConsoleSrc] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<KafkaConsoleConnection | null>(null);
  const [sidebarExpanded, setSidebarExpanded] = useState(true);
  const connectedRef = useRef(false);

  const selectedConnection = useMemo(
    () => connections.find((item) => item.id === selectedId) ?? null,
    [connections, selectedId],
  );

  const loadConnections = useCallback(async () => {
    setLoading(true);
    try {
      const list = await fetchKafkaConsoleConnections();
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
        setConsoleSrc('');
        return null;
      });
    } catch (error) {
      showApiError(error, '加载 Kafka 连接失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  const releaseKafkaConnection = useCallback((reason: 'manual' | 'unmount' | 'unload') => {
    if (!connectedRef.current) {
      return;
    }
    connectedRef.current = false;
    setConsoleSrc('');
    setConnectedId(null);
    if (reason === 'unload') {
      beaconDisconnectKafkaConsole();
      return;
    }
    disconnectKafkaConsole().catch(() => undefined);
  }, []);

  const handleEdit = useCallback((conn: KafkaConsoleConnection) => {
    setEditing(conn);
    setModalOpen(true);
  }, []);

  const handleDelete = useCallback(
    (conn: KafkaConsoleConnection) => {
      modal.confirm({
        title: '删除 Kafka 连接',
        content: `确定删除「${conn.name}」？此操作不可恢复。`,
        okText: '删除',
        okType: 'danger',
        cancelText: '取消',
        onOk: async () => {
          setDeletingId(conn.id);
          try {
            if (connectedId === conn.id) {
              releaseKafkaConnection('manual');
            }
            await deleteKafkaConsoleConnection(conn.id);
            message.success('删除成功');
            if (selectedId === conn.id) {
              setSelectedId(null);
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
    [connectedId, loadConnections, message, modal, releaseKafkaConnection, selectedId],
  );

  const treeData = useMemo<DataNode[]>(
    () =>
      connections.map((conn) => ({
        key: String(conn.id),
        title: (
          <div className="kafka-method-page__tree-node">
            <div className="kafka-method-page__tree-main">
              <span className="kafka-method-page__tree-name">{conn.name}</span>
              <span className="kafka-method-page__tree-brokers">{conn.brokers}</span>
            </div>
            <div className="kafka-method-page__tree-actions">
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

  useEffect(() => {
    connectedRef.current = connectedId != null && consoleSrc !== '';
  }, [connectedId, consoleSrc]);

  useEffect(() => {
    return registerPageCleanup((reason) => {
      releaseKafkaConnection(reason === 'unload' ? 'unload' : 'unmount');
    });
  }, [releaseKafkaConnection]);

  const handleDisconnect = () => {
    releaseKafkaConnection('manual');
    message.info('已取消连接');
  };

  const handleConnect = async () => {
    if (!selectedConnection) {
      message.warning('请先在左侧选择一个 Kafka 连接');
      return;
    }
    const hide = message.loading('正在同步集群并连接 Redpanda Console...', 0);
    setConnecting(true);
    try {
      const data = await connectKafkaConsole(selectedConnection.id, window.location.hostname);
      setConsoleSrc(resolveRedpandaOpenUrl(data.embed_url));
      setConnectedId(selectedConnection.id);
      message.success(`已连接：${selectedConnection.name}`);
    } catch (error) {
      showApiError(error, '连接 Redpanda Console 失败，请确认服务已启动（端口 8082）');
    } finally {
      hide();
      setConnecting(false);
    }
  };

  const handleCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const handleSubmit = async (values: KafkaConsoleConnectionFormValues) => {
    if (editing) {
      await updateKafkaConsoleConnection(editing.id, values);
      message.success('更新成功');
    } else {
      await createKafkaConsoleConnection(values);
      message.success('创建成功');
    }
    setModalOpen(false);
    setEditing(null);
    await loadConnections();
  };

  const isConnected = connectedId != null && consoleSrc !== '';

  return (
    <div
      className={`kafka-method-page${sidebarExpanded ? '' : ' kafka-method-page--sidebar-collapsed'}`}
    >
      <aside className="kafka-method-page__sidebar">
        <div className="kafka-method-page__sidebar-head">
          <Typography.Text strong>Kafka 连接</Typography.Text>
          <Space size={4}>
            <Button
              type="text"
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => loadConnections()}
              loading={loading}
            />
            <Button
              type="text"
              size="small"
              icon={<MenuFoldOutlined />}
              title="收起列表"
              onClick={() => setSidebarExpanded(false)}
            />
          </Space>
        </div>

        <Space className="kafka-method-page__toolbar" size={8} wrap>
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

        <div className="kafka-method-page__tree-wrap">
          {loading ? (
            <div className="kafka-method-page__tree-loading">
              <Spin />
            </div>
          ) : treeData.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无 Kafka 连接，点击新增创建"
            />
          ) : (
            <Tree
              treeData={treeData}
              defaultExpandAll
              selectedKeys={selectedId != null ? [String(selectedId)] : []}
              onSelect={(keys) => {
                const raw = keys[0];
                if (typeof raw !== 'string') {
                  return;
                }
                const nextId = Number(raw);
                setSelectedId(nextId);
                if (connectedId !== nextId) {
                  releaseKafkaConnection('manual');
                }
              }}
            />
          )}
        </div>
      </aside>

      {!sidebarExpanded ? (
        <Button
          type="text"
          className="kafka-method-page__sidebar-expand"
          icon={<MenuUnfoldOutlined />}
          title="展开列表"
          onClick={() => setSidebarExpanded(true)}
        />
      ) : null}

      <section className="kafka-method-page__main">
        {consoleSrc ? (
          <iframe title="redpanda-console" src={consoleSrc} className="embedded-console-frame" />
        ) : (
          <div className="kafka-method-page__placeholder">
            <Empty description="请从左侧选择 Kafka 连接，再点击「连接」" />
          </div>
        )}
      </section>

      <KafkaConsoleConnectionModal
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
