import {
  ApiOutlined,
  CaretDownOutlined,
  CaretRightOutlined,
  CloudServerOutlined,
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MinusOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
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
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  connectK8sCluster,
  deleteK8sCluster,
  fetchK8sClusters,
  fetchK8sPodLogs,
  fetchK8sProjects,
  fetchK8sServices,
  scaleK8sService,
} from '../api';
import K8sClusterFormModal from '../components/K8sClusterFormModal';
import type { K8sClusterConfig, K8sConnectResult, K8sPod, K8sProject, K8sService } from '../types/k8s';
import { formatDateTime } from '../utils/dateTime';

const TABLE_SCROLL_Y = 'calc(100vh - 300px)';

interface LogState {
  pod: K8sPod;
  container?: string;
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

function buildExternalServiceUrl(cluster: K8sClusterConfig | null, port?: number) {
  if (!cluster || !port) {
    return '';
  }
  try {
    const apiUrl = new URL(cluster.api_server);
    return `${apiUrl.protocol}//${apiUrl.hostname}:${port}/#/overview`;
  } catch {
    return '';
  }
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

export default function ServiceMonitorPage() {
  const { message, modal } = App.useApp();
  const [clusters, setClusters] = useState<K8sClusterConfig[]>([]);
  const [clustersLoading, setClustersLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [connectedId, setConnectedId] = useState<number | null>(null);
  const [connectInfo, setConnectInfo] = useState<K8sConnectResult | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [projects, setProjects] = useState<K8sProject[]>([]);
  const [projectLoading, setProjectLoading] = useState(false);
  const [selectedProject, setSelectedProject] = useState<string>();
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
  const [logState, setLogState] = useState<LogState | null>(null);
  const [logText, setLogText] = useState('');
  const [logLoading, setLogLoading] = useState(false);

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
  }, []);

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

  const loadProjects = useCallback(
    async (clusterId: number, preferredProject?: string) => {
      setProjectLoading(true);
      try {
        const list = await fetchK8sProjects(clusterId);
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
      } catch (error) {
        setProjects([]);
        setSelectedProject(undefined);
        setServices([]);
        message.error(getErrorMessage(error, '加载项目列表失败'));
      } finally {
        setProjectLoading(false);
      }
    },
    [loadServices, message],
  );

  useEffect(() => {
    loadClusters();
  }, [loadClusters]);

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
      await loadClusters();
      await loadProjects(selectedCluster.id, selectedProject);
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

  const openLogs = async (pod: K8sPod, container?: string) => {
    if (!connectedId) {
      return;
    }
    const nextContainer = container || pod.containers[0]?.name;
    setLogState({ pod, container: nextContainer });
    setLogText('');
    setLogLoading(true);
    try {
      const result = await fetchK8sPodLogs({
        clusterId: connectedId,
        namespace: pod.namespace,
        podName: pod.name,
        container: nextContainer,
        tailLines: 800,
      });
      setLogText(result.logs || '暂无日志');
    } catch (error) {
      setLogText(getErrorMessage(error, '加载日志失败'));
    } finally {
      setLogLoading(false);
    }
  };

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
          const externalUrl = buildExternalServiceUrl(connectedCluster, service.external_ports[0]);
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
                {externalUrl ? (
                  <a
                    href={externalUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="service-monitor-page__service-link"
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
        width: 240,
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
                    onClick={() => openLogs(row.pod, container.name)}
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
          return (
            <Space size={4}>
              <Button
                size="small"
                icon={<FileTextOutlined />}
                disabled={!service.pods.length}
                onClick={() => {
                  const pod = service.pods[0];
                  if (pod) {
                    openLogs(pod);
                  }
                }}
              >
                日志
              </Button>
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
    [connectedCluster, expandedServiceIds, operationKeys],
  );

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
            icon={<ApiOutlined />}
            loading={connecting}
            disabled={!selectedCluster}
            onClick={handleConnect}
          >
            连接
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
                <button
                  key={cluster.id}
                  type="button"
                  className={`service-monitor-page__cluster-item${
                    selected ? ' is-selected' : ''
                  }${connected ? ' is-connected' : ''}`}
                  onClick={() => {
                    setSelectedId(cluster.id);
                    if (connectedId !== cluster.id) {
                      clearRuntimeData();
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
                </button>
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
              scroll={{ x: 1660, y: TABLE_SCROLL_Y }}
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

      <Modal
        title={
          logState
            ? `${logState.pod.name}${logState.container ? ` / ${logState.container}` : ''}`
            : '容器日志'
        }
        open={Boolean(logState)}
        onCancel={() => {
          setLogState(null);
          setLogText('');
        }}
        footer={null}
        width={960}
        destroyOnHidden
      >
        {logLoading ? (
          <div className="service-monitor-page__log-loading">
            <Spin />
          </div>
        ) : (
          <pre className="service-monitor-page__log">{logText || '暂无日志'}</pre>
        )}
      </Modal>
    </div>
  );
}
