import {
  ApiOutlined,
  CaretDownOutlined,
  CaretRightOutlined,
  ClockCircleOutlined,
  CloudServerOutlined,
  DeleteOutlined,
  DisconnectOutlined,
  EditOutlined,
  FileTextOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MinusOutlined,
  NotificationOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App,
  Badge,
  Button,
  Empty,
  Input,
  Modal,
  Pagination,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  connectK8sCluster,
  createNotifyWebSocket,
  deleteK8sCluster,
  fetchK8sAlarmUnreadCount,
  fetchK8sClusters,
  fetchK8sProjects,
  fetchK8sServices,
  fetchK8sWatermarks,
  scaleK8sService,
} from '../api';
import K8sAlarmNotifyDrawer from '../components/K8sAlarmNotifyDrawer';
import K8sClusterFormModal from '../components/K8sClusterFormModal';
import K8sPodTerminalModal, { type K8sPodTerminalTarget } from '../components/K8sPodTerminalModal';
import type {
  K8sAlarmEvent,
  K8sClusterConfig,
  K8sConnectResult,
  K8sPod,
  K8sProject,
  K8sService,
  K8sWatermarkOperator,
  K8sWatermarkResult,
  K8sWatermarkValue,
} from '../types/k8s';
import { formatDateTime } from '../utils/dateTime';
import { buildExternalServiceUrl, resolveK8sServiceOpenUrlFromService } from '../utils/k8sServiceUrl';
import {
  clearK8sConnectionSession,
  readK8sConnectionSessionSnapshot,
  updateK8sConnectionSession,
} from '../utils/k8sConnectionSession';
import { registerPageCleanup } from '../utils/pageCleanup';

const TABLE_SCROLL_Y = 'calc(100vh - 300px)';

const WATERMARK_TIME_FORMATTER = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

interface WatermarkState {
  service: K8sService;
  port: number;
}

interface WatermarkTableRow {
  rowKey: string;
  operator: K8sWatermarkOperator;
  watermark: K8sWatermarkValue | null;
  isFirst: boolean;
  rowSpan: number;
}

type ServiceMonitorRow =
  | {
      rowKey: string;
      kind: 'service';
      service: K8sService;
    }
  | {
      rowKey: string;
      kind: 'pod';
      service: K8sService;
      pod: K8sPod;
    };

function getErrorMessage(error: unknown, fallback: string) {
  return (
    (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || fallback
  );
}

function renderCompactTags(values: string[], empty = '-') {
  if (!values.length) {
    return empty;
  }
  const visible = values.slice(0, 2);
  const hidden = values.slice(2);
  return (
    <Tooltip title={values.join('、')}>
      <Space size={[4, 4]} wrap>
        {visible.map((value) => (
          <Tag key={value}>{value}</Tag>
        ))}
        {hidden.length ? <Tag>+{hidden.length}</Tag> : null}
      </Space>
    </Tooltip>
  );
}

function statusColor(service: K8sService) {
  if (service.status === 'running') {
    return 'green';
  }
  if (service.ready_replicas > 0) {
    return 'orange';
  }
  return 'red';
}

function statusText(service: K8sService) {
  if (service.status === 'running') {
    return `运行中 (${service.ready_replicas}/${service.replicas})`;
  }
  if (service.ready_replicas > 0) {
    return `部分运行 (${service.ready_replicas}/${service.replicas})`;
  }
  return `未就绪 (${service.ready_replicas}/${service.replicas})`;
}

function podStatusColor(pod: K8sPod) {
  if (pod.status === 'Running') {
    return 'green';
  }
  if (pod.phase === 'Pending') {
    return 'orange';
  }
  return 'red';
}

function renderExternalPorts(
  service: K8sService,
  cluster: K8sClusterConfig | null,
  compact = false,
) {
  if (!service.external_ports.length) {
    return '-';
  }
  return (
    <Space size={[4, 4]} wrap>
      {service.external_ports.map((port) => {
        const url = buildExternalServiceUrl(cluster, port);
        return url ? (
          <a key={port} href={url} target="_blank" rel="noreferrer">
            <Tag color="blue">{port}</Tag>
          </a>
        ) : (
          <Tag key={port} color="blue">
            {port}
          </Tag>
        );
      })}
      {!compact && service.ports.length ? (
        <Tooltip title={`服务端口：${service.ports.join('、')}`}>
          <Tag>Service</Tag>
        </Tooltip>
      ) : null}
    </Space>
  );
}

function formatWatermarkTimestamp(timestamp: number) {
  if (!Number.isFinite(timestamp) || timestamp <= 0) {
    return '-';
  }
  try {
    return WATERMARK_TIME_FORMATTER.format(new Date(timestamp));
  } catch {
    return '-';
  }
}

function formatWatermarkLag(value: K8sWatermarkValue) {
  const lagMs = Math.max(0, value.lag_ms || 0);
  if (lagMs < 60000) {
    return `${Math.floor(lagMs / 1000)} 秒`;
  }
  const hours = Math.floor(lagMs / 3600000);
  const minutes = Math.floor((lagMs % 3600000) / 60000);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

function renderWatermarkCell(
  watermark: K8sWatermarkValue | null,
  content: string | number,
) {
  if (!watermark) {
    return '-';
  }
  return (
    <span
      className={`service-monitor-page__watermark-value${
        watermark.delayed ? ' is-delayed' : ''
      }`}
    >
      {content}
    </span>
  );
}

function buildWatermarkTableRows(operators: K8sWatermarkOperator[]): WatermarkTableRow[] {
  const rows: WatermarkTableRow[] = [];
  operators.forEach((operator) => {
    const watermarks = operator.watermarks.length ? operator.watermarks : [null];
    watermarks.forEach((watermark, index) => {
      rows.push({
        rowKey: `${operator.job_id}:${operator.vertex_id}:${index}`,
        operator,
        watermark,
        isFirst: index === 0,
        rowSpan: watermarks.length,
      });
    });
  });
  return rows;
}

export default function ServiceMonitorPage() {
  const { message, modal, notification } = App.useApp();
  const restoredSession = useMemo(() => readK8sConnectionSessionSnapshot(), []);
  const restoreLoadedRef = useRef(false);
  const [clusters, setClusters] = useState<K8sClusterConfig[]>([]);
  const [clustersLoading, setClustersLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(
    restoredSession.selectedId ?? restoredSession.connectedId,
  );
  const [connectedId, setConnectedId] = useState<number | null>(restoredSession.connectedId);
  const [connectInfo, setConnectInfo] = useState<K8sConnectResult | null>(restoredSession.connectInfo);
  const [connecting, setConnecting] = useState(false);
  const [projects, setProjects] = useState<K8sProject[]>(restoredSession.projects);
  const [projectLoading, setProjectLoading] = useState(false);
  const [selectedProject, setSelectedProject] = useState<string | undefined>(restoredSession.selectedProject);
  const [services, setServices] = useState<K8sService[]>([]);
  const [servicesLoading, setServicesLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<K8sClusterConfig | null>(null);
  const [sidebarExpanded, setSidebarExpanded] = useState(true);
  const [operationKeys, setOperationKeys] = useState<string[]>([]);
  const [expandedServiceIds, setExpandedServiceIds] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [terminalTarget, setTerminalTarget] = useState<K8sPodTerminalTarget | null>(null);
  const [alarmNotifyOpen, setAlarmNotifyOpen] = useState(false);
  const [alarmUnreadCount, setAlarmUnreadCount] = useState(0);
  const [alarmRefreshToken, setAlarmRefreshToken] = useState(0);
  const [watermarkState, setWatermarkState] = useState<WatermarkState | null>(null);
  const [watermarkData, setWatermarkData] = useState<K8sWatermarkResult | null>(null);
  const [watermarkLoading, setWatermarkLoading] = useState(false);
  const [watermarkError, setWatermarkError] = useState('');

  const selectedCluster = useMemo(
    () => clusters.find((item) => item.id === selectedId) ?? null,
    [clusters, selectedId],
  );
  const connectedCluster = useMemo(
    () => clusters.find((item) => item.id === connectedId) ?? null,
    [clusters, connectedId],
  );

  const clearRuntimeData = useCallback(() => {
    setConnectedId(null);
    setConnectInfo(null);
    setProjects([]);
    setSelectedProject(undefined);
    setServices([]);
    setKeyword('');
    setWatermarkState(null);
    setWatermarkData(null);
    setWatermarkError('');
    setAlarmUnreadCount(0);
    setAlarmNotifyOpen(false);
    clearK8sConnectionSession();
  }, []);

  const refreshAlarmUnreadCount = useCallback(async (clusterId: number) => {
    try {
      const count = await fetchK8sAlarmUnreadCount(clusterId);
      setAlarmUnreadCount(count);
    } catch {
      setAlarmUnreadCount(0);
    }
  }, []);

  const handleK8sAlarmEvent = useCallback(
    (event: K8sAlarmEvent) => {
      if (connectedId != null && event.cluster_id !== connectedId) {
        return;
      }
      setAlarmRefreshToken((prev) => prev + 1);
      if (event.status === 'firing' && !event.is_read) {
        setAlarmUnreadCount((prev) => prev + 1);
        notification.warning({
          message: event.title,
          description: event.summary || `${event.namespace} / ${event.service_name}`,
          placement: 'topRight',
          duration: 8,
        });
        return;
      }
      if (connectedId != null) {
        refreshAlarmUnreadCount(connectedId).catch(() => undefined);
      }
    },
    [connectedId, notification, refreshAlarmUnreadCount],
  );

  const loadClusters = useCallback(async () => {
    setClustersLoading(true);
    try {
      const list = await fetchK8sClusters();
      setClusters(list);
      setSelectedId((prev) => {
        if (prev != null && list.some((item) => item.id === prev)) {
          return prev;
        }
        return list[0]?.id ?? null;
      });
      setConnectedId((prev) => {
        if (prev != null && list.some((item) => item.id === prev)) {
          return prev;
        }
        return null;
      });
    } catch (error) {
      message.error(getErrorMessage(error, '加载 K8s 连接失败'));
    } finally {
      setClustersLoading(false);
    }
  }, [message]);

  const loadServices = useCallback(
    async (clusterId: number, project: string) => {
      setServicesLoading(true);
      try {
        const list = await fetchK8sServices(clusterId, project);
        setServices(list);
        setPage(1);
        setExpandedServiceIds((prev) => {
          const next = new Set<string>();
          const ids = new Set(list.map((item) => item.id));
          prev.forEach((id) => {
            if (ids.has(id)) {
              next.add(id);
            }
          });
          return next;
        });
      } catch (error) {
        setServices([]);
        message.error(getErrorMessage(error, '加载服务状态失败'));
      } finally {
        setServicesLoading(false);
      }
    },
    [message],
  );

  const applyProjects = useCallback(
    async (clusterId: number, list: K8sProject[], preferredProject?: string) => {
      setProjects(list);
      const nextProject =
        preferredProject && list.some((item) => item.name === preferredProject)
          ? preferredProject
          : list[0]?.name;
      setSelectedProject(nextProject);
      if (nextProject) {
        await loadServices(clusterId, nextProject);
      } else {
        setServices([]);
      }
    },
    [loadServices],
  );

  const loadProjects = useCallback(
    async (clusterId: number, preferredProject?: string) => {
      setProjectLoading(true);
      try {
        const list = await fetchK8sProjects(clusterId);
        await applyProjects(clusterId, list, preferredProject);
      } catch (error) {
        setProjects([]);
        setSelectedProject(undefined);
        setServices([]);
        message.error(getErrorMessage(error, '加载项目列表失败'));
      } finally {
        setProjectLoading(false);
      }
    },
    [applyProjects, message],
  );

  useEffect(() => {
    loadClusters();
  }, [loadClusters]);

  useEffect(() => {
    if (connectedId == null) {
      return;
    }
    updateK8sConnectionSession({
      connectedId,
      connectInfo,
      selectedId,
      selectedProject,
      projects,
    });
  }, [connectedId, connectInfo, selectedId, selectedProject, projects]);

  useEffect(() => {
    if (restoreLoadedRef.current || restoredSession.connectedId == null) {
      return;
    }
    restoreLoadedRef.current = true;
    const clusterId = restoredSession.connectedId;
    if (restoredSession.selectedProject) {
      loadServices(clusterId, restoredSession.selectedProject).catch(() => undefined);
      return;
    }
    loadProjects(clusterId, restoredSession.selectedProject).catch(() => undefined);
  }, [loadProjects, loadServices, restoredSession.connectedId, restoredSession.selectedProject]);

  useEffect(() => {
    return registerPageCleanup((reason) => {
      if (reason === 'unload') {
        clearK8sConnectionSession();
      }
    });
  }, []);

  useEffect(() => {
    if (connectedId) {
      refreshAlarmUnreadCount(connectedId).catch(() => undefined);
    } else {
      setAlarmUnreadCount(0);
    }
  }, [connectedId, refreshAlarmUnreadCount]);

  useEffect(() => {
    const handle = createNotifyWebSocket({
      onK8sAlarm: handleK8sAlarmEvent,
    });
    return () => {
      handle.close();
    };
  }, [handleK8sAlarmEvent]);

  const handleDisconnect = () => {
    clearRuntimeData();
    message.info('已取消连接');
  };

  const handleConnect = async () => {
    if (!selectedCluster) {
      message.warning('请先选择一个 K8s 连接');
      return;
    }
    setConnecting(true);
    try {
      const result = await connectK8sCluster(selectedCluster.id);
      setConnectedId(selectedCluster.id);
      setConnectInfo(result);
      setClusters((prev) =>
        prev.map((item) =>
          item.id === selectedCluster.id
            ? {
                ...item,
                last_connected_at: result.last_connected_at || new Date().toISOString(),
              }
            : item,
        ),
      );
      if (Array.isArray(result.projects)) {
        setProjectLoading(true);
        try {
          await applyProjects(selectedCluster.id, result.projects, selectedProject);
        } finally {
          setProjectLoading(false);
        }
      } else {
        await loadProjects(selectedCluster.id, selectedProject);
      }
      message.success(`${selectedCluster.name} 连接成功`);
    } catch (error) {
      clearRuntimeData();
      message.error(getErrorMessage(error, '连接 K8s 集群失败'));
    } finally {
      setConnecting(false);
    }
  };

  const handleRefresh = async () => {
    if (!connectedId) {
      await loadClusters();
      return;
    }
    await loadProjects(connectedId, selectedProject);
  };

  const handleProjectChange = async (project: string) => {
    setSelectedProject(project);
    if (connectedId) {
      await loadServices(connectedId, project);
    }
  };

  const handleSaved = (cluster: K8sClusterConfig) => {
    setModalOpen(false);
    setEditing(null);
    setSelectedId(cluster.id);
    loadClusters();
  };

  const handleDelete = (cluster: K8sClusterConfig) => {
    modal.confirm({
      title: '删除 K8s 连接',
      content: `确定删除“${cluster.name}”？`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        await deleteK8sCluster(cluster.id);
        message.success('删除成功');
        if (selectedId === cluster.id || connectedId === cluster.id) {
          clearRuntimeData();
          setSelectedId(null);
        }
        await loadClusters();
      },
    });
  };

  const handleScale = async (service: K8sService, delta: number) => {
    if (!connectedId || !service.workload_kind || !service.workload_name) {
      return;
    }
    const key = `${service.id}:${delta}`;
    setOperationKeys((prev) => [...prev, key]);
    try {
      const result = await scaleK8sService(connectedId, {
        namespace: service.namespace,
        workload_kind: service.workload_kind,
        workload_name: service.workload_name,
        delta,
      });
      message.success(result.message);
      await loadServices(connectedId, service.namespace);
    } catch (error) {
      message.error(getErrorMessage(error, '调整副本数失败'));
    } finally {
      setOperationKeys((prev) => prev.filter((item) => item !== key));
    }
  };

  const openTerminal = (pod: K8sPod, container?: string) => {
    if (!connectedId) {
      return;
    }
    const nextContainer = container || pod.containers[0]?.name;
    setTerminalTarget({
      namespace: pod.namespace,
      podName: pod.name,
      container: nextContainer,
    });
  };

  const openWatermarks = useCallback(
    async (service: K8sService) => {
      if (!connectedId) {
        return;
      }
      const port = service.external_ports[0];
      if (!port) {
        return;
      }
      setWatermarkState({ service, port });
      setWatermarkData(null);
      setWatermarkError('');
      setWatermarkLoading(true);
      try {
        const result = await fetchK8sWatermarks({
          clusterId: connectedId,
          namespace: service.namespace,
          serviceName: service.service_name,
          port,
        });
        setWatermarkData(result);
      } catch (error) {
        setWatermarkError(getErrorMessage(error, '加载 Watermark 数据失败'));
      } finally {
        setWatermarkLoading(false);
      }
    },
    [connectedId],
  );

  const filteredServices = useMemo(() => {
    const text = keyword.trim().toLowerCase();
    if (!text) {
      return services;
    }
    return services.filter((service) => {
      const haystack = [
        service.service_name,
        service.workload_name,
        service.project,
        ...service.ports,
        ...service.external_ports.map(String),
        ...service.nodes,
        ...service.pod_ips,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(text);
    });
  }, [keyword, services]);

  useEffect(() => {
    setPage(1);
  }, [keyword, selectedProject]);

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(filteredServices.length / pageSize));
    if (page > maxPage) {
      setPage(maxPage);
    }
  }, [filteredServices.length, page, pageSize]);

  const paginatedServices = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredServices.slice(start, start + pageSize);
  }, [filteredServices, page, pageSize]);

  const tableRows = useMemo<ServiceMonitorRow[]>(() => {
    const rows: ServiceMonitorRow[] = [];
    paginatedServices.forEach((service) => {
      rows.push({ rowKey: service.id, kind: 'service', service });
      if (expandedServiceIds.has(service.id)) {
        service.pods.forEach((pod) => {
          rows.push({
            rowKey: `${service.id}:pod:${pod.name}`,
            kind: 'pod',
            service,
            pod,
          });
        });
      }
    });
    return rows;
  }, [expandedServiceIds, paginatedServices]);

  const toggleServiceExpand = (service: K8sService) => {
    if (!service.pods.length) {
      return;
    }
    setExpandedServiceIds((prev) => {
      const next = new Set(prev);
      if (next.has(service.id)) {
        next.delete(service.id);
      } else {
        next.add(service.id);
      }
      return next;
    });
  };

  const watermarkTableRows = useMemo(
    () => buildWatermarkTableRows(watermarkData?.items ?? []),
    [watermarkData],
  );

  const watermarkColumns = useMemo<TableColumnsType<WatermarkTableRow>>(
    () => [
      {
        title: '算子名称',
        width: 300,
        onCell: (row) => (row.isFirst ? { rowSpan: row.rowSpan } : { rowSpan: 0 }),
        render: (_, row) =>
          row.isFirst ? (
            <div className="service-monitor-page__watermark-operator">
              <Typography.Text strong>
                {row.operator.operator_name || row.operator.vertex_id}
              </Typography.Text>
              {row.operator.job_name ? (
                <Typography.Text type="secondary">{row.operator.job_name}</Typography.Text>
              ) : null}
              {row.operator.error ? (
                <Typography.Text type="danger">{row.operator.error}</Typography.Text>
              ) : null}
            </div>
          ) : null,
      },
      {
        title: '所有 Watermark 时间戳',
        width: 280,
        render: (_, row) =>
          renderWatermarkCell(row.watermark, row.watermark?.raw || row.watermark?.timestamp || '-'),
      },
      {
        title: '转换后的时间点',
        width: 280,
        render: (_, row) =>
          renderWatermarkCell(
            row.watermark,
            row.watermark ? formatWatermarkTimestamp(row.watermark.timestamp) : '-',
          ),
      },
      {
        title: '与当前时间相比',
        width: 200,
        render: (_, row) =>
          renderWatermarkCell(
            row.watermark,
            row.watermark ? formatWatermarkLag(row.watermark) : '-',
          ),
      },
    ],
    [],
  );

  const serviceColumns = useMemo<TableColumnsType<ServiceMonitorRow>>(
    () => [
      {
        title: '服务名称',
        dataIndex: 'service_name',
        width: 360,
        render: (_, row) => {
          if (row.kind === 'pod') {
            return (
              <div className="service-monitor-page__pod-name">
                <span className="service-monitor-page__pod-indent" />
                <CloudServerOutlined />
                <div>
                  <Typography.Text strong>{row.pod.name}</Typography.Text>
                  <Typography.Text type="secondary">
                    容器组 / {row.pod.phase || '-'} / 重启 {row.pod.restart_count}
                  </Typography.Text>
                </div>
              </div>
            );
          }
          const { service } = row;
          const expanded = expandedServiceIds.has(service.id);
          const serviceUrl = resolveK8sServiceOpenUrlFromService(connectedCluster, service);
          const kubesphereUrl =
            connectedCluster?.provider === 'kubesphere' &&
            Boolean(service.workload_kind && service.workload_name)
              ? serviceUrl
              : '';
          return (
            <div className="service-monitor-page__service-name">
              {service.pods.length ? (
                <Button
                  type="text"
                  size="small"
                  className="service-monitor-page__expand-btn"
                  icon={expanded ? <CaretDownOutlined /> : <CaretRightOutlined />}
                  onClick={() => toggleServiceExpand(service)}
                />
              ) : (
                <span className="service-monitor-page__expand-placeholder" />
              )}
              <span className="service-monitor-page__service-icon" />
              <div>
                {serviceUrl ? (
                  <a
                    href={serviceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="service-monitor-page__service-link"
                    title={kubesphereUrl ? '在 KubeSphere 控制台中打开' : undefined}
                  >
                    <Typography.Text strong>{service.service_name}</Typography.Text>
                  </a>
                ) : (
                  <Typography.Text strong>{service.service_name}</Typography.Text>
                )}
                <div className="service-monitor-page__service-meta">
                  {service.workload_kind && service.workload_name ? (
                    <Typography.Text type="secondary">
                      {service.workload_kind} / {service.workload_name}
                    </Typography.Text>
                  ) : (
                    <Typography.Text type="secondary">Service / 未关联工作负载</Typography.Text>
                  )}
                  {service.service_type ? <Tag>{service.service_type}</Tag> : null}
                </div>
              </div>
            </div>
          );
        },
      },
      {
        title: '运行状态',
        dataIndex: 'status',
        width: 160,
        render: (_, row) =>
          row.kind === 'pod' ? (
            <Badge color={podStatusColor(row.pod)} text={row.pod.status || '-'} />
          ) : (
            <Badge color={statusColor(row.service)} text={statusText(row.service)} />
          ),
      },
      {
        title: '项目',
        dataIndex: 'project',
        width: 160,
        render: (_, row) => row.service.project,
      },
      {
        title: '外部访问端口',
        dataIndex: 'external_ports',
        width: 160,
        render: (_, row) =>
          row.kind === 'pod' ? '-' : renderExternalPorts(row.service, connectedCluster, true),
      },
      {
        title: '节点',
        dataIndex: 'nodes',
        width: 220,
        render: (_, row) =>
          row.kind === 'pod' ? row.pod.node || '-' : renderCompactTags(row.service.nodes),
      },
      {
        title: '容器组 IP 地址',
        dataIndex: 'pod_ips',
        width: 220,
        render: (_, row) =>
          row.kind === 'pod' ? row.pod.pod_ip || '-' : renderCompactTags(row.service.pod_ips),
      },
      {
        title: '更新时间',
        dataIndex: 'updated_at',
        width: 180,
        render: (_, row) =>
          row.kind === 'pod'
            ? formatDateTime(row.pod.updated_at) || '-'
            : formatDateTime(row.service.updated_at) || '-',
      },
      {
        title: '操作',
        width: 320,
        fixed: 'right',
        render: (_, row) => {
          if (row.kind === 'pod') {
            return (
              <Space size={[4, 4]} wrap>
                {row.pod.containers.map((container) => (
                  <Button
                    key={container.name}
                    size="small"
                    icon={<FileTextOutlined />}
                    onClick={() => openTerminal(row.pod, container.name)}
                  >
                    {container.name}
                  </Button>
                ))}
              </Space>
            );
          }

          const { service } = row;
          const increaseKey = `${service.id}:1`;
          const decreaseKey = `${service.id}:-1`;
          const watermarkButtonLoading =
            watermarkLoading && watermarkState?.service.id === service.id;
          return (
            <Space size={[4, 4]} wrap>
              <Button
                size="small"
                icon={<FileTextOutlined />}
                disabled={!service.pods.length}
                onClick={() => {
                  const pod = service.pods[0];
                  if (pod) {
                    openTerminal(pod);
                  }
                }}
              >
                终端
              </Button>
              {service.external_ports.length ? (
                <Button
                  size="small"
                  icon={<ClockCircleOutlined />}
                  loading={watermarkButtonLoading}
                  onClick={() => {
                    openWatermarks(service).catch(() => undefined);
                  }}
                >
                  Watermark
                </Button>
              ) : null}
              <Tooltip title={service.scalable ? '副本数 +1' : '未找到可扩缩容工作负载'}>
                <Button
                  size="small"
                  icon={<PlusOutlined />}
                  disabled={!service.scalable}
                  loading={operationKeys.includes(increaseKey)}
                  onClick={() => handleScale(service, 1)}
                />
              </Tooltip>
              <Tooltip title={service.scalable ? '副本数 -1' : '未找到可扩缩容工作负载'}>
                <Button
                  size="small"
                  icon={<MinusOutlined />}
                  disabled={!service.scalable || service.replicas <= 0}
                  loading={operationKeys.includes(decreaseKey)}
                  onClick={() => handleScale(service, -1)}
                />
              </Tooltip>
            </Space>
          );
        },
      },
    ],
    [connectedCluster, expandedServiceIds, openWatermarks, operationKeys, watermarkLoading, watermarkState],
  );

  const isConnectedToSelected = connectedId != null && selectedCluster?.id === connectedId;

  return (
    <div
      className={`service-monitor-page${
        sidebarExpanded ? '' : ' service-monitor-page--sidebar-collapsed'
      }`}
    >
      <aside className="service-monitor-page__sidebar">
        <div className="service-monitor-page__sidebar-head">
          <Typography.Text strong>K8s 连接</Typography.Text>
          <Space size={4}>
            <Button
              type="text"
              size="small"
              icon={<ReloadOutlined />}
              loading={clustersLoading}
              onClick={() => loadClusters()}
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

        <Space className="service-monitor-page__toolbar" size={8} wrap>
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
          >
            新增
          </Button>
          <Button
            type="primary"
            size="small"
            icon={isConnectedToSelected ? <DisconnectOutlined /> : <ApiOutlined />}
            loading={connecting}
            disabled={!selectedCluster}
            onClick={() => {
              if (isConnectedToSelected) {
                handleDisconnect();
                return;
              }
              handleConnect().catch(() => undefined);
            }}
          >
            {isConnectedToSelected ? '取消连接' : '连接'}
          </Button>
        </Space>

        <div className="service-monitor-page__cluster-list">
          {clustersLoading ? (
            <div className="service-monitor-page__loading">
              <Spin />
            </div>
          ) : clusters.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 K8s 连接" />
          ) : (
            clusters.map((cluster) => {
              const selected = selectedId === cluster.id;
              const connected = connectedId === cluster.id;
              return (
                <div
                  key={cluster.id}
                  role="button"
                  tabIndex={0}
                  className={`service-monitor-page__cluster-item${
                    selected ? ' is-selected' : ''
                  }${connected ? ' is-connected' : ''}`}
                  onClick={() => {
                    setSelectedId(cluster.id);
                    if (connectedId !== cluster.id) {
                      clearRuntimeData();
                    }
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      setSelectedId(cluster.id);
                      if (connectedId !== cluster.id) {
                        clearRuntimeData();
                      }
                    }
                  }}
                >
                  <span className="service-monitor-page__cluster-status">
                    <Badge color={connected ? 'green' : 'default'} />
                  </span>
                  <span className="service-monitor-page__cluster-main">
                    <Typography.Text strong ellipsis>
                      {cluster.name}
                    </Typography.Text>
                    <Typography.Text type="secondary" ellipsis>
                      {cluster.api_server}
                    </Typography.Text>
                    <span className="service-monitor-page__cluster-tags">
                      <Tag>{cluster.provider}</Tag>
                      <Tag>{cluster.auth_type === 'token' ? 'Token' : '账号密码'}</Tag>
                    </span>
                  </span>
                  <span className="service-monitor-page__cluster-actions">
                    <Button
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      title="编辑"
                      onClick={(event) => {
                        event.stopPropagation();
                        setEditing(cluster);
                        setModalOpen(true);
                      }}
                    />
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      title="删除"
                      onClick={(event) => {
                        event.stopPropagation();
                        handleDelete(cluster);
                      }}
                    />
                  </span>
                </div>
              );
            })
          )}
        </div>
      </aside>

      {!sidebarExpanded ? (
        <Button
          type="text"
          className="service-monitor-page__sidebar-expand"
          icon={<MenuUnfoldOutlined />}
          title="展开列表"
          onClick={() => setSidebarExpanded(true)}
        />
      ) : null}

      <section className="service-monitor-page__main">
        {!connectedCluster ? (
          <div className="service-monitor-page__placeholder">
            <Empty description="请从左侧选择 K8s 连接，再点击“连接”" />
          </div>
        ) : (
          <>
            <div className="service-monitor-page__main-head">
              <div className="service-monitor-page__main-title">
                <Typography.Title level={5}>{connectedCluster.name}</Typography.Title>
                <Space size={[6, 6]} wrap>
                  <Tag color="blue">{connectedCluster.provider}</Tag>
                  {connectInfo?.version ? <Tag>{connectInfo.version}</Tag> : null}
                  {connectInfo?.namespace_count ? <Tag>{connectInfo.namespace_count} 项目</Tag> : null}
                </Space>
              </div>
              <Space size={10} wrap>
                <Select
                  showSearch
                  optionFilterProp="label"
                  loading={projectLoading}
                  value={selectedProject}
                  placeholder="选择项目"
                  style={{ width: 220 }}
                  options={projects.map((project) => ({
                    value: project.name,
                    label: project.name,
                  }))}
                  onChange={(value) => {
                    handleProjectChange(value).catch(() => undefined);
                  }}
                />
                <Input
                  allowClear
                  prefix={<SearchOutlined />}
                  placeholder="搜索服务、节点、IP"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  style={{ width: 280 }}
                />
                <Badge count={alarmUnreadCount} size="small" offset={[-4, 4]}>
                  <Button
                    icon={<NotificationOutlined />}
                    disabled={!connectedId}
                    onClick={() => setAlarmNotifyOpen(true)}
                  >
                    站内报警
                  </Button>
                </Badge>
                <Button
                  icon={<ReloadOutlined />}
                  loading={projectLoading || servicesLoading}
                  onClick={() => {
                    handleRefresh().catch(() => undefined);
                  }}
                >
                  刷新
                </Button>
              </Space>
            </div>

            <Table<ServiceMonitorRow>
              rowKey="rowKey"
              className="service-monitor-page__table"
              dataSource={tableRows}
              columns={serviceColumns}
              loading={servicesLoading}
              pagination={false}
              scroll={{ x: 1740, y: TABLE_SCROLL_Y }}
              rowClassName={(row) =>
                row.kind === 'pod' ? 'service-monitor-page__row--pod' : ''
              }
            />
            <div className="service-monitor-page__pagination">
              <Pagination
                current={page}
                pageSize={pageSize}
                total={filteredServices.length}
                showSizeChanger
                pageSizeOptions={[10, 20, 50]}
                showTotal={(total) => `共 ${total} 个服务`}
                onChange={(nextPage, nextPageSize) => {
                  setPage(nextPage);
                  if (nextPageSize) {
                    setPageSize(nextPageSize);
                  }
                }}
              />
            </div>
          </>
        )}
      </section>

      <K8sClusterFormModal
        open={modalOpen}
        cluster={editing}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onSaved={handleSaved}
      />

      <K8sAlarmNotifyDrawer
        open={alarmNotifyOpen}
        clusterId={connectedId}
        onClose={() => setAlarmNotifyOpen(false)}
        onUnreadChange={setAlarmUnreadCount}
        refreshToken={alarmRefreshToken}
      />

      <K8sPodTerminalModal
        open={Boolean(terminalTarget)}
        clusterId={connectedId}
        target={terminalTarget}
        onClose={() => setTerminalTarget(null)}
      />

      <Modal
        title={
          watermarkState
            ? `Watermark / ${watermarkState.service.service_name}:${watermarkState.port}`
            : 'Watermark'
        }
        open={Boolean(watermarkState)}
        onCancel={() => {
          setWatermarkState(null);
          setWatermarkData(null);
          setWatermarkError('');
        }}
        footer={null}
        width={1120}
        destroyOnHidden
      >
        {watermarkLoading ? (
          <div className="service-monitor-page__log-loading">
            <Spin />
          </div>
        ) : watermarkError ? (
          <Alert type="error" showIcon message="加载 Watermark 数据失败" description={watermarkError} />
        ) : (
          <>
            {watermarkData ? (
              <div className="service-monitor-page__watermark-meta">
                <Space size={[6, 6]} wrap>
                  <Tag>{watermarkData.jobs_count} 个任务</Tag>
                  <Tag>{watermarkData.items.length} 个算子</Tag>
                  <Tag>端口 {watermarkData.port}</Tag>
                  {formatDateTime(watermarkData.generated_at) ? (
                    <Tag>{formatDateTime(watermarkData.generated_at)}</Tag>
                  ) : null}
                  {watermarkData.flink_url ? (
                    <a href={watermarkData.flink_url} target="_blank" rel="noreferrer">
                      打开 Flink
                    </a>
                  ) : null}
                </Space>
              </div>
            ) : null}
            <Table<WatermarkTableRow>
              rowKey="rowKey"
              className="service-monitor-page__watermark-table"
              dataSource={watermarkTableRows}
              columns={watermarkColumns}
              pagination={false}
              size="small"
              scroll={{ x: 1060, y: 'min(56vh, 560px)' }}
              rowClassName={(row) =>
                row.watermark?.delayed ? 'service-monitor-page__watermark-row--delayed' : ''
              }
              locale={{ emptyText: '暂无 Watermark 数据' }}
            />
          </>
        )}
      </Modal>
    </div>
  );
}
