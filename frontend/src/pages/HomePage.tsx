import { EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Layout, Select, Space, Typography, message } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  createConnection,
  createLogsWebSocket,
  deleteConnection,
  fetchHome,
  fetchLogs,
  markLogRead,
  openOmnidbConsole,
  openSshwiftyConsole,
  reorderConnections,
  updateConnection,
} from '../api';
import ActivityLogPanel from '../components/ActivityLogPanel';
import ConnectionFormModal from '../components/ConnectionFormModal';
import SchemaChangeModal from '../components/SchemaChangeModal';
import ConnectionSection from '../components/ConnectionSection';
import {
  buildLabelColorMap,
  buildLabelIconIndexMap,
  buildLabelOrderMap,
  dictToOptions,
  useDict,
} from '../hooks/useDict';
import type { ActivityLog, Connection, ConnectionFormValues, HomeGroup } from '../types';
import { openOmnidbInNewTab } from '../utils/omnidb';
import { openMqttConsole } from '../utils/mqttNavigation';
import { openSshwiftyInNewTab } from '../utils/sshwifty';
import { isSchemaChangeLog } from '../utils/schemaChangeLog';

const { Content, Sider } = Layout;

const EXPAND_KEY = 'quicknav-collapse';
const PROJECT_KEY = 'quicknav-project';
const ENV_KEY = 'quicknav-environment';

function loadStorageNumber(key: string): number | null {
  const raw = localStorage.getItem(key);
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function loadGroupExpanded(groupId: number): boolean {
  return localStorage.getItem(`${EXPAND_KEY}-group-${groupId}`) !== 'false';
}

export default function HomePage() {
  const { items: projectItems, options: projectOptions, idMap: projectIdMap } = useDict('project');
  const { items: envItems, options: environmentOptions, idMap: envIdMap } = useDict('environment');
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

  const [project, setProject] = useState<number | null>(() => loadStorageNumber(PROJECT_KEY));
  const [environment, setEnvironment] = useState<number | null>(() => loadStorageNumber(ENV_KEY));
  const [groups, setGroups] = useState<HomeGroup[]>([]);
  const [expandedMap, setExpandedMap] = useState<Record<number, boolean>>({});
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Connection | null>(null);
  const [schemaChangeLog, setSchemaChangeLog] = useState<ActivityLog | null>(null);
  const [schemaChangeOpen, setSchemaChangeOpen] = useState(false);
  const resolvedProject = useMemo(() => {
    if (project && projectOptions.some((o) => o.value === project)) return project;
    return projectOptions[0]?.value ?? null;
  }, [project, projectOptions]);

  const resolvedEnvironment = useMemo(() => {
    if (environment && environmentOptions.some((o) => o.value === environment)) return environment;
    return environmentOptions[0]?.value ?? null;
  }, [environment, environmentOptions]);

  const loadData = useCallback(async () => {
    if (resolvedProject == null || resolvedEnvironment == null) return;
    setLoading(true);
    try {
      const [home, logList] = await Promise.all([
        fetchHome(resolvedProject, resolvedEnvironment),
        fetchLogs({ project: resolvedProject, environment: resolvedEnvironment, limit: 50 }),
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
    } catch {
      message.error('加载数据失败');
    } finally {
      setLoading(false);
    }
  }, [resolvedProject, resolvedEnvironment]);

  useEffect(() => {
    if (resolvedProject != null) localStorage.setItem(PROJECT_KEY, String(resolvedProject));
    if (resolvedEnvironment != null) localStorage.setItem(ENV_KEY, String(resolvedEnvironment));
    loadData();
  }, [resolvedProject, resolvedEnvironment, loadData]);

  useEffect(() => {
    if (project == null && projectOptions[0]) setProject(projectOptions[0].value);
  }, [project, projectOptions]);

  useEffect(() => {
    if (environment == null && environmentOptions[0]) setEnvironment(environmentOptions[0].value);
  }, [environment, environmentOptions]);

  useEffect(() => {
    if (resolvedProject == null || resolvedEnvironment == null) return;
    const ws = createLogsWebSocket((log) => {
      if (
        log.project === String(resolvedProject) &&
        log.environment === String(resolvedEnvironment)
      ) {
        setLogs((prev) => [log, ...prev.filter((item) => item.id !== log.id)].slice(0, 50));
      }
    });
    return () => ws.close();
  }, [resolvedProject, resolvedEnvironment]);

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
    } catch {
      message.error('排序保存失败');
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
    } catch {
      message.error('保存失败');
    }
  };

  const handleLogClick = async (log: ActivityLog) => {
    if (isSchemaChangeLog(log)) {
      setSchemaChangeLog(log);
      setSchemaChangeOpen(true);
    }
    if (log.is_read) return;
    try {
      const updated = await markLogRead(log.id);
      setLogs((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch {
      message.error('标记已读失败');
    }
  };

  const handleDelete = async (conn: Connection) => {
    try {
      await deleteConnection(conn.id);
      message.success('删除成功');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  const handleOpenEmbedded = async (conn: Connection, kind: 'database' | 'terminal' | 'mqtt') => {
    if (kind === 'mqtt') {
      try {
        openMqttConsole(conn.id);
      } catch (error) {
        if (error instanceof Error && error.message === 'browser blocked popup') {
          message.warning('浏览器拦截了新标签页，请允许弹窗后重试');
        }
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
        message.error('打开数据库控制台失败，请确认 OmniDB 已启动（端口 8081）');
      } else {
        const detail =
          error && typeof error === 'object' && 'response' in error
            ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : undefined;
        message.error(
          detail || '打开终端失败，请确认 Sshwifty 已启动（端口 8182）且连接已保存密码',
        );
      }
    } finally {
      hide();
    }
  };

  const selectProjectOptions = projectOptions.length ? projectOptions : dictToOptions(projectItems);
  const selectEnvironmentOptions = environmentOptions.length
    ? environmentOptions
    : dictToOptions(envItems);
  const selectGroupOptions = groupOptions.length ? groupOptions : dictToOptions(groupItems);

  const projectLabel = resolvedProject != null ? projectIdMap[resolvedProject] ?? resolvedProject : '';
  const environmentLabel =
    resolvedEnvironment != null ? envIdMap[resolvedEnvironment] ?? resolvedEnvironment : '';

  return (
    <div className="home-page">
      <div className="tab-page-toolbar">
        <Space align="center" size={12}>
          <Typography.Title level={5} style={{ margin: 0 }}>
            快捷导航
          </Typography.Title>
          <Button
            icon={<EditOutlined />}
            type={editMode ? 'primary' : 'default'}
            onClick={() => setEditMode((prev) => !prev)}
          >
            {editMode ? '退出编辑' : '编辑'}
          </Button>
        </Space>
        <Space wrap>
          <Select
            style={{ width: 180 }}
            value={resolvedProject ?? undefined}
            options={selectProjectOptions}
            onChange={setProject}
            placeholder="选择项目"
          />
          <Select
            style={{ width: 160 }}
            value={resolvedEnvironment ?? undefined}
            options={selectEnvironmentOptions}
            onChange={setEnvironment}
            placeholder="选择环境"
          />
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
            disabled={!labelOptions.length || !selectGroupOptions.length}
          >
            新增连接
          </Button>
        </Space>
      </div>

      <Layout className="home-layout">
        <Content className="home-content">
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
                envIdMap={envIdMap}
              />
            </div>
          ))}
        </Content>
        <Sider width={300} className="home-log-sider" theme="light">
          <ActivityLogPanel logs={logs} onItemClick={handleLogClick} />
        </Sider>
      </Layout>

      <ConnectionFormModal
        open={modalOpen}
        connection={editing}
        projectOptions={selectProjectOptions}
        environmentOptions={selectEnvironmentOptions}
        labelOptions={labelOptions}
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
      <SchemaChangeModal
        log={schemaChangeLog}
        open={schemaChangeOpen}
        onClose={() => {
          setSchemaChangeOpen(false);
          setSchemaChangeLog(null);
        }}
      />
    </div>
  );
}
