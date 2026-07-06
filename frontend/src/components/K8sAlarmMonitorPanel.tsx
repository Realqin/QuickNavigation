import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import {
  App,
  Button,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Typography,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchK8sAlarmMonitorGroups,
  fetchK8sAlarmMonitorServices,
  saveK8sAlarmMonitorService,
  syncK8sAlarmMonitor,
  syncK8sAlarmMonitorGroup,
  updateK8sAlarmMonitorGroup,
} from '../api';
import type {
  K8sAlarmMonitorGroup,
  K8sAlarmMonitorService,
  K8sRestartMonitorOption,
} from '../types/k8s';
import {
  K8S_RESTART_MONITOR_OPTIONS,
  getRestartMonitorLabel,
} from '../types/k8s';

interface K8sAlarmMonitorPanelProps {
  open: boolean;
  clusterId: number | null;
  onClose: () => void;
}

interface ServiceEditDraft {
  restart_monitor: K8sRestartMonitorOption;
  watermarkDraft: number | null;
}

type EnabledFilter = 'all' | 'enabled' | 'disabled';

const SERVICE_TABLE_SCROLL_Y = 'min(56vh, 520px)';

function getErrorMessage(error: unknown, fallback: string) {
  return (
    (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || fallback
  );
}

function formatWatermarkMinutes(value: number | null | undefined) {
  if (value == null || value <= 0) {
    return '-';
  }
  return `${value} 分钟`;
}

function buildDraftsFromServices(services: K8sAlarmMonitorService[]) {
  const drafts: Record<string, ServiceEditDraft> = {};
  services.forEach((item) => {
    drafts[item.service_name] = {
      restart_monitor: item.restart_monitor,
      watermarkDraft: item.watermark_minutes,
    };
  });
  return drafts;
}

export default function K8sAlarmMonitorPanel({
  open,
  clusterId,
  onClose,
}: K8sAlarmMonitorPanelProps) {
  const { message } = App.useApp();
  const [groups, setGroups] = useState<K8sAlarmMonitorGroup[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [groupKeyword, setGroupKeyword] = useState('');
  const [groupEnabledFilter, setGroupEnabledFilter] = useState<EnabledFilter>('all');
  const [groupPage, setGroupPage] = useState(1);
  const [groupPageSize, setGroupPageSize] = useState(10);
  const [activeNamespace, setActiveNamespace] = useState<string | null>(null);
  const [viewOpen, setViewOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [services, setServices] = useState<K8sAlarmMonitorService[]>([]);
  const [servicesLoading, setServicesLoading] = useState(false);
  const [serviceKeyword, setServiceKeyword] = useState('');
  const [editDrafts, setEditDrafts] = useState<Record<string, ServiceEditDraft>>({});
  const [savingAll, setSavingAll] = useState(false);
  const [syncingAll, setSyncingAll] = useState(false);
  const [switchingNamespace, setSwitchingNamespace] = useState<string | null>(null);

  const loadGroups = useCallback(async () => {
    if (!clusterId) {
      return;
    }
    setGroupsLoading(true);
    try {
      const list = await fetchK8sAlarmMonitorGroups(clusterId);
      setGroups(list);
      setGroupPage(1);
    } catch (error) {
      message.error(getErrorMessage(error, '加载报警监控分组失败'));
    } finally {
      setGroupsLoading(false);
    }
  }, [clusterId, message]);

  const handleSyncAllGroups = async () => {
    if (!clusterId) {
      return;
    }
    setSyncingAll(true);
    try {
      const result = await syncK8sAlarmMonitor(clusterId);
      await loadGroups();
      message.success(`已同步 ${result.groups_count} 个分组`);
    } catch (error) {
      message.error(getErrorMessage(error, '同步报警监控分组失败'));
    } finally {
      setSyncingAll(false);
    }
  };

  const loadServices = useCallback(
    async (namespace: string) => {
      if (!clusterId) {
        return;
      }
      setServicesLoading(true);
      try {
        const list = await fetchK8sAlarmMonitorServices(clusterId, namespace);
        setServices(list);
        setEditDrafts(buildDraftsFromServices(list));
        return list;
      } catch (error) {
        message.error(getErrorMessage(error, '加载服务监控配置失败'));
        return [];
      } finally {
        setServicesLoading(false);
      }
    },
    [clusterId, message],
  );

  const refreshNamespace = useCallback(
    async (namespace: string) => {
      if (!clusterId) {
        return;
      }
      setServicesLoading(true);
      try {
        const result = await syncK8sAlarmMonitorGroup(clusterId, namespace);
        await loadServices(namespace);
        message.success(`已同步服务列表，共 ${result.services_count} 个服务`);
      } catch (error) {
        message.error(getErrorMessage(error, '同步服务列表失败'));
      } finally {
        setServicesLoading(false);
      }
    },
    [clusterId, loadServices, message],
  );

  useEffect(() => {
    if (open && clusterId) {
      loadGroups().catch(() => undefined);
    }
  }, [open, clusterId, loadGroups]);

  useEffect(() => {
    if (!open) {
      setViewOpen(false);
      setEditOpen(false);
      setActiveNamespace(null);
      setServices([]);
      setEditDrafts({});
      setGroupKeyword('');
      setGroupEnabledFilter('all');
      setServiceKeyword('');
    }
  }, [open]);

  useEffect(() => {
    setGroupPage(1);
  }, [groupKeyword, groupEnabledFilter]);

  const filteredGroups = useMemo(() => {
    const keyword = groupKeyword.trim().toLowerCase();
    return groups.filter((item) => {
      if (groupEnabledFilter === 'enabled' && !item.enabled) {
        return false;
      }
      if (groupEnabledFilter === 'disabled' && item.enabled) {
        return false;
      }
      if (keyword && !item.namespace.toLowerCase().includes(keyword)) {
        return false;
      }
      return true;
    });
  }, [groupEnabledFilter, groupKeyword, groups]);

  const paginatedGroups = useMemo(() => {
    const start = (groupPage - 1) * groupPageSize;
    return filteredGroups.slice(start, start + groupPageSize);
  }, [filteredGroups, groupPage, groupPageSize]);

  const filteredServices = useMemo(() => {
    const keyword = serviceKeyword.trim().toLowerCase();
    if (!keyword) {
      return services;
    }
    return services.filter((item) => item.service_name.toLowerCase().includes(keyword));
  }, [serviceKeyword, services]);

  const handleToggleGroup = async (namespace: string, enabled: boolean) => {
    if (!clusterId) {
      return;
    }
    setSwitchingNamespace(namespace);
    try {
      const updated = await updateK8sAlarmMonitorGroup(clusterId, namespace, enabled);
      setGroups((prev) =>
        prev.map((item) => (item.namespace === namespace ? { ...item, ...updated } : item)),
      );
      message.success(enabled ? '已开启分组监控' : '已关闭分组监控');
    } catch (error) {
      message.error(getErrorMessage(error, '更新分组监控开关失败'));
    } finally {
      setSwitchingNamespace(null);
    }
  };

  const openView = (namespace: string) => {
    setActiveNamespace(namespace);
    setServiceKeyword('');
    setViewOpen(true);
    loadServices(namespace).catch(() => undefined);
  };

  const openEdit = (namespace: string) => {
    setActiveNamespace(namespace);
    setServiceKeyword('');
    setEditOpen(true);
    loadServices(namespace).catch(() => undefined);
  };

  const handleSaveAll = async () => {
    if (!clusterId || !activeNamespace) {
      return;
    }
    const serviceNames = services.map((item) => item.service_name);
    if (!serviceNames.length) {
      message.warning('暂无可保存的服务');
      return;
    }
    setSavingAll(true);
    try {
      await Promise.all(
        serviceNames.map((serviceName) => {
          const draft = editDrafts[serviceName] || {
            restart_monitor: 'none' as K8sRestartMonitorOption,
            watermarkDraft: null,
          };
          return saveK8sAlarmMonitorService(clusterId, activeNamespace, serviceName, {
            restart_monitor: draft.restart_monitor,
            watermark_minutes: draft.watermarkDraft,
          });
        }),
      );
      await loadServices(activeNamespace);
      message.success('监控配置已保存');
    } catch (error) {
      message.error(getErrorMessage(error, '保存监控配置失败'));
    } finally {
      setSavingAll(false);
    }
  };

  const groupColumns = useMemo<TableColumnsType<K8sAlarmMonitorGroup>>(
    () => [
      {
        title: '分组',
        dataIndex: 'namespace',
        ellipsis: true,
      },
      {
        title: '开关',
        dataIndex: 'enabled',
        width: 100,
        render: (enabled: boolean, row) => (
          <Switch
            checked={enabled}
            loading={switchingNamespace === row.namespace}
            onChange={(checked) => {
              handleToggleGroup(row.namespace, checked).catch(() => undefined);
            }}
          />
        ),
      },
      {
        title: '操作',
        width: 140,
        render: (_, row) => (
          <Space size={12}>
            <Typography.Link
              onClick={() => {
                openView(row.namespace);
              }}
            >
              查看
            </Typography.Link>
            <Typography.Link
              onClick={() => {
                openEdit(row.namespace);
              }}
            >
              编辑
            </Typography.Link>
          </Space>
        ),
      },
    ],
    [switchingNamespace],
  );

  const viewColumns = useMemo<TableColumnsType<K8sAlarmMonitorService>>(
    () => [
      {
        title: '服务名',
        dataIndex: 'service_name',
        ellipsis: true,
      },
      {
        title: '监控重启时间',
        dataIndex: 'restart_monitor',
        width: 140,
        render: (value: K8sRestartMonitorOption) => getRestartMonitorLabel(value),
      },
      {
        title: '监控 Watermark',
        dataIndex: 'watermark_minutes',
        width: 160,
        render: (value: number | null) => formatWatermarkMinutes(value),
      },
    ],
    [],
  );

  const editColumns = useMemo<TableColumnsType<K8sAlarmMonitorService>>(
    () => [
      {
        title: '服务名',
        dataIndex: 'service_name',
        ellipsis: true,
      },
      {
        title: '监控重启时间',
        dataIndex: 'restart_monitor',
        width: 180,
        render: (_, row) => {
          const draft = editDrafts[row.service_name];
          return (
            <Select
              style={{ width: '100%' }}
              value={draft?.restart_monitor || 'none'}
              options={K8S_RESTART_MONITOR_OPTIONS}
              onChange={(value: K8sRestartMonitorOption) => {
                setEditDrafts((prev) => ({
                  ...prev,
                  [row.service_name]: {
                    restart_monitor: value,
                    watermarkDraft: prev[row.service_name]?.watermarkDraft ?? null,
                  },
                }));
              }}
            />
          );
        },
      },
      {
        title: '监控 Watermark',
        dataIndex: 'watermark_minutes',
        width: 220,
        render: (_, row) => {
          const draft = editDrafts[row.service_name];
          return (
            <Space size={8}>
              <InputNumber
                min={1}
                max={10080}
                precision={0}
                placeholder="分钟"
                value={draft?.watermarkDraft ?? undefined}
                onChange={(value) => {
                  setEditDrafts((prev) => ({
                    ...prev,
                    [row.service_name]: {
                      restart_monitor: prev[row.service_name]?.restart_monitor || 'none',
                      watermarkDraft: typeof value === 'number' ? value : null,
                    },
                  }));
                }}
              />
              <Typography.Text type="secondary">分钟</Typography.Text>
            </Space>
          );
        },
      },
    ],
    [editDrafts],
  );

  const serviceSearchInput = (
    <Input
      allowClear
      prefix={<SearchOutlined />}
      placeholder="搜索服务名"
      value={serviceKeyword}
      onChange={(event) => setServiceKeyword(event.target.value)}
      style={{ width: 240 }}
    />
  );

  return (
    <>
      <Modal
        title="报警监控"
        open={open}
        onCancel={onClose}
        footer={null}
        width={760}
        destroyOnHidden
        className="k8s-alarm-monitor-modal"
      >
        <div className="k8s-alarm-monitor-modal__toolbar">
          <Button
            icon={<ReloadOutlined />}
            loading={syncingAll}
            onClick={() => {
              handleSyncAllGroups().catch(() => undefined);
            }}
          >
            同步全部分组
          </Button>
          <Typography.Text type="secondary">
            仅拉取项目列表入库；服务列表请在分组内点「刷新」同步
          </Typography.Text>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索分组名"
            value={groupKeyword}
            onChange={(event) => setGroupKeyword(event.target.value)}
            style={{ width: 220 }}
          />
          <Select<EnabledFilter>
            value={groupEnabledFilter}
            style={{ width: 140 }}
            options={[
              { value: 'all', label: '全部开关' },
              { value: 'enabled', label: '已启用' },
              { value: 'disabled', label: '未启用' },
            ]}
            onChange={setGroupEnabledFilter}
          />
        </div>
        <Table<K8sAlarmMonitorGroup>
          rowKey="namespace"
          loading={groupsLoading}
          dataSource={paginatedGroups}
          columns={groupColumns}
          pagination={{
            current: groupPage,
            pageSize: groupPageSize,
            total: filteredGroups.length,
            showSizeChanger: true,
            pageSizeOptions: [10, 20, 50],
            onChange: (page, pageSize) => {
              setGroupPage(page);
              if (pageSize) {
                setGroupPageSize(pageSize);
              }
            },
          }}
          size="small"
          locale={{ emptyText: '暂无匹配的分组' }}
        />
      </Modal>

      <Modal
        title={activeNamespace ? `查看监控 / ${activeNamespace}` : '查看监控'}
        open={viewOpen}
        onCancel={() => {
          setViewOpen(false);
        }}
        footer={null}
        width={860}
        destroyOnHidden
        className="k8s-alarm-monitor-modal"
      >
        <div className="k8s-alarm-monitor-modal__toolbar">
          <Button
            icon={<ReloadOutlined />}
            loading={servicesLoading}
            onClick={() => {
              if (activeNamespace) {
                refreshNamespace(activeNamespace).catch(() => undefined);
              }
            }}
          >
            刷新
          </Button>
          {serviceSearchInput}
        </div>
        {servicesLoading ? (
          <div className="k8s-alarm-monitor-modal__loading">
            <Spin />
          </div>
        ) : (
          <Table<K8sAlarmMonitorService>
            rowKey="service_name"
            dataSource={filteredServices}
            columns={viewColumns}
            pagination={false}
            size="small"
            scroll={{ y: SERVICE_TABLE_SCROLL_Y }}
            locale={{ emptyText: '暂无服务数据' }}
          />
        )}
      </Modal>

      <Modal
        title={activeNamespace ? `编辑监控 / ${activeNamespace}` : '编辑监控'}
        open={editOpen}
        onCancel={() => {
          setEditOpen(false);
        }}
        onOk={() => {
          handleSaveAll().catch(() => undefined);
        }}
        okText="保存"
        confirmLoading={savingAll}
        cancelText="取消"
        width={960}
        destroyOnHidden
        className="k8s-alarm-monitor-modal"
      >
        <div className="k8s-alarm-monitor-modal__toolbar">
          <Button
            icon={<ReloadOutlined />}
            loading={servicesLoading}
            onClick={() => {
              if (activeNamespace) {
                refreshNamespace(activeNamespace).catch(() => undefined);
              }
            }}
          >
            刷新
          </Button>
          {serviceSearchInput}
          <Typography.Text type="secondary">
            刷新将从集群同步服务名称入库，已保存的监控配置不会丢失。
          </Typography.Text>
        </div>
        {servicesLoading ? (
          <div className="k8s-alarm-monitor-modal__loading">
            <Spin />
          </div>
        ) : (
          <Table<K8sAlarmMonitorService>
            rowKey="service_name"
            dataSource={filteredServices}
            columns={editColumns}
            pagination={false}
            size="small"
            scroll={{ x: 760, y: SERVICE_TABLE_SCROLL_Y }}
            locale={{ emptyText: '暂无服务数据' }}
          />
        )}
      </Modal>
    </>
  );
}
