import { EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Space, Typography, message } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  createConnection,
  createLogsWebSocket,
  deleteConnection,
  fetchHome,
  fetchLogs,
  markLogRead,
  openOmnidbConsole,
  openRedpandaConsole,
  openRedisinsightConsole,
  openSshwiftyConsole,
  reorderConnections,
  updateConnection,
} from '../api';
import ActivityLogPanel from '../components/ActivityLogPanel';
import ConnectionFormModal from '../components/ConnectionFormModal';
import ConnectionSection from '../components/ConnectionSection';
import {
  buildLabelColorMap,
  buildLabelIconIndexMap,
  buildLabelOrderMap,
  useDict,
} from '../hooks/useDict';
import { useActivityLogDetail } from '../hooks/useActivityLogDetail';
import type { ActivityLog, Connection, ConnectionFormValues, HomeGroup } from '../types';
import { openOmnidbInNewTab } from '../utils/omnidb';
import { openMqttConsole } from '../utils/mqttNavigation';
import { openRedpandaInNewTab } from '../utils/redpanda';
import { openRedisinsightInNewTab } from '../utils/redisinsight';
import { openSshwiftyInNewTab } from '../utils/sshwifty';
import { showApiError } from '../utils/apiError';
import { useAuth } from '../contexts/AuthContext';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { filterLabelOptionsByPermission } from '../utils/connectionPermissions';

const EXPAND_KEY = 'quicknav-collapse';
const HOME_LOG_LIMIT = 8;

function loadGroupExpanded(groupId: number): boolean {
  return localStorage.getItem(`${EXPAND_KEY}-group-${groupId}`) !== 'false';
}

export default function HomePage() {
  const { user } = useAuth();
  const {
    globalProject: resolvedProject,
    globalEnvironment: resolvedEnvironment,
    projectIdMap,
    environmentIdMap,
    projectOptions,
    environmentOptions,
    globalVersion,
  } = useWorkspace();
  const { items: labelItems, options: labelOptions, idMap: labelIdMap } = useDict('label');
  const {
    items: groupItems,
    options: groupOptions,
  } = useDict('connection_group');

  const labelColorMap = useMemo(() => buildLabelColorMap(labelItems), [labelItems]);
  const labelOrderMap = useMemo(() => buildLabelOrderMap(labelItems), [labelItems]);
  const labelIconIndexMap = useMemo(() => buildLabelIconIndexMap(labelItems), [labelItems]);

  const projectGroupId = useMemo(
    () => groupItems.find((item) => item.is_system)?.id,
    [groupItems],
  );

  const [groups, setGroups] = useState<HomeGroup[]>([]);
  const [expandedMap, setExpandedMap] = useState<Record<number, boolean>>({});
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Connection | null>(null);
  const { openActivityLogDetail, detailModals } = useActivityLogDetail();

  const loadData = useCallback(async () => {
    if (resolvedProject == null || resolvedEnvironment == null) return;
    setLoading(true);
    try {
      const [home, logList] = await Promise.all([
        fetchHome(resolvedProject, resolvedEnvironment),
        fetchLogs({ project: resolvedProject, environment: resolvedEnvironment, limit: HOME_LOG_LIMIT }),
      ]);
      setGroups(home.groups);
      setExpandedMap((prev) => {
        const next = { ...prev };
        home.groups.forEach((group) => {
          if (next[group.id] === undefined) {
            next[group.id] = loadGroupExpanded(group.id);
          }
        });
        return next;
      });
      setLogs(logList);
    } catch (error) {
      showApiError(error, '加载数据失败');
    } finally {
      setLoading(false);
    }
  }, [resolvedProject, resolvedEnvironment]);

  useEffect(() => {
    loadData();
  }, [loadData, globalVersion]);

  useEffect(() => {
    if (resolvedProject == null || resolvedEnvironment == null) return;
    const handle = createLogsWebSocket(
      (log) => {
        setLogs((prev) => [log, ...prev.filter((item) => item.id !== log.id)].slice(0, HOME_LOG_LIMIT));
      },
      { project: resolvedProject, environment: resolvedEnvironment },
    );
    return () => handle.close();
  }, [resolvedProject, resolvedEnvironment, globalVersion]);

  const handleExpandChange = (key: string, expanded: boolean) => {
    localStorage.setItem(`${EXPAND_KEY}-${key}`, String(expanded));
    const groupId = Number(key.replace('group-', ''));
    if (Number.isFinite(groupId)) {
      setExpandedMap((prev) => ({ ...prev, [groupId]: expanded }));
    }
  };

  const updateGroupConnections = (groupId: number, connections: Connection[]) => {
    setGroups((prev) =>
      prev.map((group) => (group.id === groupId ? { ...group, connections } : group)),
    );
  };

  const applyReorder = async (
    scope: string,
    groupId: number,
    list: Connection[],
  ) => {
    const items = list.map((item, index) => ({ id: item.id, sort_order: index }));
    updateGroupConnections(
      groupId,
      list.map((item, index) => ({ ...item, sort_order: index })),
    );
    try {
      await reorderConnections(scope, items);
    } catch (error) {
      showApiError(error, '排序保存失败');
      loadData();
    }
  };

  const handleSubmit = async (values: ConnectionFormValues) => {
    try {
      if (editing) {
        await updateConnection(editing.id, values);
        message.success('更新成功');
      } else {
        await createConnection(values);
        message.success('创建成功');
      }
      setModalOpen(false);
      setEditing(null);
      loadData();
    } catch (error) {
      showApiError(error, '保存失败');
    }
  };

  const handleLogClick = async (log: ActivityLog) => {
    openActivityLogDetail(log);
    if (log.is_read) return;
    try {
      const updated = await markLogRead(log.id);
      setLogs((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch (error) {
      showApiError(error, '标记已读失败');
    }
  };

  const handleDelete = async (conn: Connection) => {
    try {
      await deleteConnection(conn.id);
      message.success('删除成功');
      loadData();
    } catch (error) {
      showApiError(error, '删除失败');
    }
  };

  const handleOpenEmbedded = async (
    conn: Connection,
    kind: 'database' | 'terminal' | 'mqtt' | 'kafka' | 'redis',
  ) => {
    if (kind === 'mqtt') {
      const hide = message.loading('正在打开 MQTT 控制台...', 0);
      try {
        await openMqttConsole(conn.id);
      } catch (error) {
        if (error instanceof Error && error.message === 'browser blocked popup') {
          message.warning('浏览器拦截了新标签页，请允许弹窗后重试');
        } else {
          showApiError(error, '打开 MQTT 控制台失败');
        }
      } finally {
        hide();
      }
      return;
    }

    if (kind === 'kafka') {
      const hide = message.loading('正在同步 Kafka 集群并打开 Redpanda Console...', 0);
      try {
        await openRedpandaInNewTab(openRedpandaConsole, conn.id);
      } catch (error) {
        if (error instanceof Error && error.message === 'browser blocked popup') {
          message.warning('浏览器拦截了新标签页，请允许弹窗后重试');
        } else {
          showApiError(error, '打开 Redpanda Console 失败，请确认服务已启动（端口 8082）');
        }
      } finally {
        hide();
      }
      return;
    }

    if (kind === 'redis') {
      const hide = message.loading('正在同步 Redis 连接并打开 RedisInsight...', 0);
      try {
        await openRedisinsightInNewTab(openRedisinsightConsole, conn.id);
      } catch (error) {
        if (error instanceof Error && error.message === 'browser blocked popup') {
          message.warning('浏览器拦截了新标签页，请允许弹窗后重试');
        } else {
          showApiError(error, '打开 RedisInsight 失败，请确认服务已启动（端口 5540）');
        }
      } finally {
        hide();
      }
      return;
    }

    const hide = message.loading(
      kind === 'database'
        ? '正在同步数据库并自动连接 OmniDB...'
        : '正在打开终端并自动连接 SSH...',
      0,
    );
    try {
      if (kind === 'database') {
        await openOmnidbInNewTab(openOmnidbConsole, conn.id);
      } else {
        await openSshwiftyInNewTab(openSshwiftyConsole, conn.id);
      }
    } catch (error) {
      if (error instanceof Error && error.message === 'browser blocked popup') {
        message.warning('浏览器拦截了新标签页，请允许弹窗后重试');
      } else if (kind === 'database') {
        showApiError(error, '打开数据库控制台失败，请确认 OmniDB 已启动（端口 8081）');
      } else {
        showApiError(error, '打开终端失败，请确认 Sshwifty 已启动（端口 8182）且连接已保存密码');
      }
    } finally {
      hide();
    }
  };

  const selectProjectOptions = projectOptions;
  const selectEnvironmentOptions = environmentOptions;
  const selectGroupOptions = groupOptions;
  const allowedLabelOptions = useMemo(
    () => filterLabelOptionsByPermission(user, labelOptions, labelItems),
    [labelItems, labelOptions, user],
  );

  const projectLabel = resolvedProject != null ? projectIdMap[resolvedProject] ?? resolvedProject : '';
  const environmentLabel =
    resolvedEnvironment != null
      ? environmentIdMap[resolvedEnvironment] ?? resolvedEnvironment
      : '';

  return (
    <div className="home-page">
      <div className="tab-page-toolbar">
        <Space align="center" size={12}>
          <Typography.Title level={5} style={{ margin: 0 }}>
            快捷导航
          </Typography.Title>
          <Typography.Text type="secondary">
            {projectLabel} / {environmentLabel}
          </Typography.Text>
          <Button
            icon={<EditOutlined />}
            type={editMode ? 'primary' : 'default'}
            onClick={() => setEditMode((prev) => !prev)}
          >
            {editMode ? '退出编辑' : '编辑'}
          </Button>
        </Space>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={loadData} loading={loading}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
            disabled={!allowedLabelOptions.length || !selectGroupOptions.length}
          >
            新增连接
          </Button>
        </Space>
      </div>

      <div className="home-page__body">
        <div className="home-page__scroll">
          {groups.map((group, index) => (
            <div key={group.id}>
              {index > 0 ? <div style={{ height: 16 }} /> : null}
              <ConnectionSection
                title={
                  group.is_project_group
                    ? `${group.name} · ${projectLabel} / ${environmentLabel}`
                    : group.name
                }
                panelKey={`group-${group.id}`}
                connections={group.connections}
                expanded={expandedMap[group.id] ?? true}
                editMode={editMode}
                onExpandChange={handleExpandChange}
                onReorder={(list) =>
                  applyReorder(
                    group.is_project_group
                      ? `group:${group.id}:project:${resolvedProject}:${resolvedEnvironment}`
                      : `group:${group.id}`,
                    group.id,
                    list,
                  )
                }
                onEdit={(conn) => {
                  setEditing(conn);
                  setModalOpen(true);
                }}
                onDelete={handleDelete}
                onOpen={handleOpenEmbedded}
                labelItems={labelItems}
                labelIdMap={labelIdMap}
                labelColorMap={labelColorMap}
                labelIconIndexMap={labelIconIndexMap}
                labelOrderMap={labelOrderMap}
                projectIdMap={projectIdMap}
                envIdMap={environmentIdMap}
              />
            </div>
          ))}
        </div>
        <aside className="home-page__aside">
          <ActivityLogPanel logs={logs} onItemClick={handleLogClick} />
        </aside>
      </div>

      <ConnectionFormModal
        open={modalOpen}
        connection={editing}
        projectOptions={selectProjectOptions}
        environmentOptions={selectEnvironmentOptions}
        labelOptions={allowedLabelOptions}
        labelItems={labelItems}
        groupOptions={selectGroupOptions}
        groupItems={groupItems}
        defaultProjects={resolvedProject != null ? [resolvedProject] : []}
        defaultEnvironments={resolvedEnvironment != null ? [resolvedEnvironment] : []}
        defaultGroupId={projectGroupId}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onSubmit={handleSubmit}
      />
      {detailModals}
    </div>
  );
}
