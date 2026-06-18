import {
  CaretDownOutlined,
  CaretRightOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  HistoryOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { App, Button, Empty, Form, Input, Select, Space, Spin, Tag, Tree, Typography } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchApiMonitorEndpoint,
  fetchApiMonitorFilterOptions,
  fetchApiMonitorGroups,
  fetchApiMonitorModules,
  fetchApiMonitorSpec,
} from '../api';
import ApiMonitorEnvPresetModal from '../components/ApiMonitorEnvPresetModal';
import type {
  ApiMonitorDetailTab,
  ApiMonitorEndpoint,
  ApiMonitorEndpointSummary,
  ApiMonitorFilterOptions,
  ApiMonitorGroups,
  ApiMonitorModuleSummary,
  ApiMonitorSpec,
} from '../types/apiMonitor';
import ApiMonitorCasesPanel from '../features/api-monitor/ApiMonitorCasesPanel';
import ApiMonitorChangePanel from '../features/api-monitor/ApiMonitorChangePanel';
import ApiMonitorDebugPanel from '../features/api-monitor/ApiMonitorDebugPanel';
import ApiMonitorDocPanel from '../features/api-monitor/ApiMonitorDocPanel';
import { readApiMonitorEnvPreset } from '../features/api-monitor/apiMonitorEnvPreset';
import { useDictGroup } from '../hooks/useDict';

const METHOD_COLORS: Record<string, string> = {
  GET: '#49cc90',
  POST: '#61affe',
  PUT: '#fca130',
  PATCH: '#50e3c2',
  DELETE: '#f93e3e',
  HEAD: '#9012fe',
  OPTIONS: '#0d5aa7',
};

const FILTER_PANEL_STORAGE_KEY = 'api-monitor-filters-expanded';

function readFiltersExpanded(): boolean {
  const stored = localStorage.getItem(FILTER_PANEL_STORAGE_KEY);
  if (stored == null) {
    return true;
  }
  return stored === 'true';
}

const EMPTY_FILTER_OPTIONS: ApiMonitorFilterOptions = {
  projects: [],
  environments: [],
  names: [],
};

function MethodBadge({ method }: { method: string }) {
  return (
    <span className="api-monitor-page__method" style={{ background: METHOD_COLORS[method] || '#909399' }}>
      {method}
    </span>
  );
}

function pickFirst<T>(items: T[] | undefined): T | undefined {
  return items && items.length > 0 ? items[0] : undefined;
}

function mapEndpointSummary(endpoint: ApiMonitorEndpoint): ApiMonitorEndpointSummary {
  const author = endpoint.source?.author;
  let summary = endpoint.summary || endpoint.path || '';
  if (author) {
    summary = `${summary} · ${author}`;
  }
  return {
    id: endpoint.id,
    method: endpoint.method,
    path: endpoint.path,
    summary,
  };
}

function buildEndpointsByTag(spec: ApiMonitorSpec): Record<string, ApiMonitorEndpointSummary[]> {
  const result: Record<string, ApiMonitorEndpointSummary[]> = {};
  for (const group of spec.groups) {
    const tag = group.tag || 'default';
    result[tag] = (group.endpoints || [])
      .map(mapEndpointSummary)
      .sort((left, right) => left.path.localeCompare(right.path) || left.method.localeCompare(right.method));
  }
  return result;
}

function filterEndpointSummaries(
  endpoints: ApiMonitorEndpointSummary[],
  keyword: string,
): ApiMonitorEndpointSummary[] {
  const text = keyword.trim().toLowerCase();
  if (!text) {
    return endpoints;
  }
  return endpoints.filter(
    (endpoint) =>
      endpoint.summary.toLowerCase().includes(text) ||
      endpoint.path.toLowerCase().includes(text) ||
      endpoint.method.toLowerCase().includes(text),
  );
}

function excludeRemovedEndpoints(
  endpoints: ApiMonitorEndpointSummary[],
  removedKeys: ReadonlySet<string>,
): ApiMonitorEndpointSummary[] {
  if (removedKeys.size === 0) {
    return endpoints;
  }
  return endpoints.filter((endpoint) => !removedKeys.has(endpoint.id));
}

function buildEndpointTreeKey(groupTag: string, endpointId: string): string {
  return `${groupTag}::${endpointId}`;
}

function parseEndpointIdFromTreeKey(key: string): string {
  const separatorIndex = key.indexOf('::');
  return separatorIndex >= 0 ? key.slice(separatorIndex + 2) : key;
}

function findSelectedTreeKeys(treeData: DataNode[], endpointId?: string | null): string[] {
  if (!endpointId) {
    return [];
  }
  for (const group of treeData) {
    for (const child of group.children ?? []) {
      const key = String(child.key ?? '');
      if (parseEndpointIdFromTreeKey(key) === endpointId) {
        return [key];
      }
    }
  }
  return [];
}

function findFirstVisibleEndpoint(
  endpointsByTag: Record<string, ApiMonitorEndpointSummary[]>,
  groups: Array<{ tag: string }>,
  removedKeys: ReadonlySet<string>,
): ApiMonitorEndpointSummary | undefined {
  for (const group of groups) {
    const endpoint = pickFirst(excludeRemovedEndpoints(endpointsByTag[group.tag] ?? [], removedKeys));
    if (endpoint) {
      return endpoint;
    }
  }
  return undefined;
}

async function resolveDefaultFilters(
  overrides?: Partial<{ project: number; environment: number; name: string }>,
) {
  const root = await fetchApiMonitorFilterOptions();
  const project = overrides?.project ?? pickFirst(root.projects)?.id;
  if (project == null) {
    return { options: root, project: undefined, environment: undefined, serviceId: undefined };
  }

  const withProject = await fetchApiMonitorFilterOptions({ project });
  const environment = overrides?.environment ?? pickFirst(withProject.environments)?.id;
  if (environment == null) {
    return { options: withProject, project, environment: undefined, serviceId: undefined };
  }

  const withEnvironment = await fetchApiMonitorFilterOptions({ project, environment });
  const serviceId =
    overrides?.name && withEnvironment.names.some((item) => item.id === overrides.name)
      ? overrides.name
      : pickFirst(withEnvironment.names)?.id;

  return {
    options: withEnvironment,
    project,
    environment,
    serviceId,
  };
}

export default function ApiMonitorPage() {
  const { message } = App.useApp();
  const projects = useDictGroup('project');
  const environments = useDictGroup('environment');
  const [filterForm] = Form.useForm();
  const [filterOptions, setFilterOptions] = useState<ApiMonitorFilterOptions>(EMPTY_FILTER_OPTIONS);
  const [filterLoading, setFilterLoading] = useState(true);
  const [serviceInfo, setServiceInfo] = useState<ApiMonitorGroups | null>(null);
  const [modules, setModules] = useState<ApiMonitorModuleSummary[]>([]);
  const [modulesLoading, setModulesLoading] = useState(false);
  const [selectedModule, setSelectedModule] = useState<string | null>(null);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [endpointsByTag, setEndpointsByTag] = useState<Record<string, ApiMonitorEndpointSummary[]>>({});
  const [removedEndpointKeys, setRemovedEndpointKeys] = useState<string[]>([]);
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);
  const [selectedEndpoint, setSelectedEndpoint] = useState<ApiMonitorEndpoint | null>(null);
  const [endpointLoading, setEndpointLoading] = useState(false);
  const [detailTab, setDetailTab] = useState<ApiMonitorDetailTab>('doc');
  const [keyword, setKeyword] = useState('');
  const [sidebarExpanded, setSidebarExpanded] = useState(true);
  const [filtersExpanded, setFiltersExpanded] = useState(readFiltersExpanded);
  const [envPresetOpen, setEnvPresetOpen] = useState(false);
  const [envPreset, setEnvPreset] = useState(readApiMonitorEnvPreset);
  const suppressFilterChangeRef = useRef(false);
  const selectedModuleRef = useRef<string | null>(null);
  const selectedEndpointIdRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    selectedModuleRef.current = selectedModule;
  }, [selectedModule]);

  useEffect(() => {
    selectedEndpointIdRef.current = selectedEndpoint?.id;
  }, [selectedEndpoint?.id]);

  const selectedServiceId = Form.useWatch('name', filterForm) as string | undefined;
  const selectedProjectId = Form.useWatch('project', filterForm) as number | undefined;
  const selectedEnvironmentId = Form.useWatch('environment', filterForm) as number | undefined;

  const clearServiceData = useCallback(() => {
    setServiceInfo(null);
    setModules([]);
    setSelectedModule(null);
    setEndpointsByTag({});
    setRemovedEndpointKeys([]);
    setExpandedKeys([]);
    setSelectedEndpoint(null);
  }, []);

  const loadEndpointDetail = useCallback(
    async (serviceId: string, endpointId: string) => {
      setEndpointLoading(true);
      try {
        const detail = await fetchApiMonitorEndpoint(serviceId, endpointId);
        setSelectedEndpoint(detail);
      } catch (error) {
        setSelectedEndpoint(null);
        const detail =
          (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          '加载接口详情失败';
        message.warning(detail);
      } finally {
        setEndpointLoading(false);
      }
    },
    [message],
  );

  const loadModuleData = useCallback(
    async (
      serviceId: string,
      module: string,
      options?: { keepSelection?: boolean },
    ) => {
      setGroupsLoading(true);
      const previousEndpointId = options?.keepSelection ? selectedEndpointIdRef.current : undefined;
      try {
        const [groupsData, spec] = await Promise.all([
          fetchApiMonitorGroups(serviceId, module),
          fetchApiMonitorSpec(serviceId, module),
        ]);
        const byTag = buildEndpointsByTag(spec);
        setServiceInfo(groupsData);
        setEndpointsByTag(byTag);
        setRemovedEndpointKeys(groupsData.removed_endpoint_keys ?? []);

        if (previousEndpointId) {
          const matchedTag = Object.entries(byTag).find(([, endpoints]) =>
            endpoints.some((item) => item.id === previousEndpointId),
          )?.[0];
          if (matchedTag) {
            setExpandedKeys((prev) =>
              prev.includes(`group:${matchedTag}`) ? prev : [...prev, `group:${matchedTag}`],
            );
            await loadEndpointDetail(serviceId, previousEndpointId);
            return;
          }
        }

        const firstTag = pickFirst(groupsData.groups)?.tag;
        if (firstTag) {
          setExpandedKeys([`group:${firstTag}`]);
          const firstEndpoint = pickFirst(byTag[firstTag]);
          if (firstEndpoint) {
            await loadEndpointDetail(serviceId, firstEndpoint.id);
          } else {
            setSelectedEndpoint(null);
          }
        } else {
          setExpandedKeys([]);
          setSelectedEndpoint(null);
        }
      } catch (error) {
        setServiceInfo(null);
        setEndpointsByTag({});
        setRemovedEndpointKeys([]);
        setExpandedKeys([]);
        setSelectedEndpoint(null);
        const detail =
          (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          '接口文档尚未生成，请先在日志订阅中启用并获取代码';
        message.warning(detail);
      } finally {
        setGroupsLoading(false);
      }
    },
    [loadEndpointDetail, message],
  );

  const loadModules = useCallback(
    async (serviceId: string, options?: { keepSelection?: boolean }) => {
      setModulesLoading(true);
      try {
        const data = await fetchApiMonitorModules(serviceId);
        setModules(data.modules);
        const currentModule = options?.keepSelection ? selectedModuleRef.current : null;
        const moduleStillExists =
          currentModule && data.modules.some((item) => item.name === currentModule)
            ? currentModule
            : null;
        const nextModule = moduleStillExists ?? pickFirst(data.modules)?.name ?? null;
        setSelectedModule(nextModule);
        return nextModule;
      } catch (error) {
        setModules([]);
        setSelectedModule(null);
        const detail =
          (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          '加载服务列表失败';
        message.warning(detail);
        return null;
      } finally {
        setModulesLoading(false);
      }
    },
    [message],
  );

  const applyDefaultFilters = useCallback(
    async (overrides?: Partial<{ project: number; environment: number; name: string }>) => {
      setFilterLoading(true);
      suppressFilterChangeRef.current = true;
      try {
        const resolved = await resolveDefaultFilters(overrides);
        setFilterOptions(resolved.options);
        filterForm.setFieldsValue({
          project: resolved.project,
          environment: resolved.environment,
          name: resolved.serviceId,
        });
        return resolved.serviceId;
      } catch {
        message.error('加载筛选项失败');
        setFilterOptions(EMPTY_FILTER_OPTIONS);
        return undefined;
      } finally {
        suppressFilterChangeRef.current = false;
        setFilterLoading(false);
      }
    },
    [filterForm, message],
  );

  const bootstrapPage = useCallback(async () => {
    const serviceId = await applyDefaultFilters();
    if (serviceId) {
      const module = await loadModules(serviceId, { keepSelection: true });
      if (module) {
        await loadModuleData(serviceId, module, { keepSelection: true });
      } else {
        clearServiceData();
      }
    } else {
      clearServiceData();
    }
  }, [applyDefaultFilters, clearServiceData, loadModules, loadModuleData]);

  useEffect(() => {
    bootstrapPage().catch(() => undefined);
    // 仅首次进入页面时加载，避免 bootstrapPage 引用变化导致循环刷新
  }, []);

  const handleFilterChange = async (changed: Partial<Record<string, unknown>>) => {
    if (suppressFilterChangeRef.current) {
      return;
    }
    if ('project' in changed) {
      const project = changed.project as number | undefined;
      if (project == null) {
        clearServiceData();
        return;
      }
      const serviceId = await applyDefaultFilters({ project });
      if (serviceId) {
        const module = await loadModules(serviceId);
        if (module) {
          await loadModuleData(serviceId, module);
        } else {
          clearServiceData();
        }
      } else {
        clearServiceData();
      }
      return;
    }

    if ('environment' in changed) {
      const project = filterForm.getFieldValue('project') as number | undefined;
      const environment = changed.environment as number | undefined;
      if (project == null || environment == null) {
        clearServiceData();
        return;
      }
      const serviceId = await applyDefaultFilters({ project, environment });
      if (serviceId) {
        const module = await loadModules(serviceId);
        if (module) {
          await loadModuleData(serviceId, module);
        } else {
          clearServiceData();
        }
      } else {
        clearServiceData();
      }
      return;
    }

    if ('name' in changed) {
      const serviceId = changed.name as string | undefined;
      if (serviceId) {
        const module = await loadModules(serviceId);
        if (module) {
          await loadModuleData(serviceId, module);
        } else {
          clearServiceData();
        }
      } else {
        clearServiceData();
      }
    }
  };

  const handleModuleChange = async (module: string) => {
    if (!selectedServiceId) {
      return;
    }
    setSelectedModule(module);
    setKeyword('');
    setExpandedKeys([]);
    await loadModuleData(selectedServiceId, module);
  };

  useEffect(() => {
    if (!keyword.trim() || !serviceInfo?.groups.length) {
      return;
    }
    const removedKeySet = detailTab === 'cases' ? new Set(removedEndpointKeys) : new Set<string>();
    const matchingKeys = serviceInfo.groups
      .filter((group) =>
        filterEndpointSummaries(
          excludeRemovedEndpoints(endpointsByTag[group.tag] ?? [], removedKeySet),
          keyword,
        ).length > 0,
      )
      .map((group) => `group:${group.tag}`);
    if (matchingKeys.length) {
      setExpandedKeys(matchingKeys);
    }
  }, [detailTab, endpointsByTag, keyword, removedEndpointKeys, serviceInfo?.groups]);

  const removedEndpointKeySet = useMemo(
    () => new Set(removedEndpointKeys),
    [removedEndpointKeys],
  );

  const treeEndpointsByTag = useMemo(() => {
    if (detailTab !== 'cases') {
      return endpointsByTag;
    }
    const result: Record<string, ApiMonitorEndpointSummary[]> = {};
    for (const [tag, endpoints] of Object.entries(endpointsByTag)) {
      result[tag] = excludeRemovedEndpoints(endpoints, removedEndpointKeySet);
    }
    return result;
  }, [detailTab, endpointsByTag, removedEndpointKeySet]);

  useEffect(() => {
    if (detailTab !== 'cases' || !selectedServiceId || !serviceInfo?.groups.length) {
      return;
    }
    const currentId = selectedEndpointIdRef.current;
    if (!currentId || !removedEndpointKeySet.has(currentId)) {
      return;
    }
    const nextEndpoint = findFirstVisibleEndpoint(
      endpointsByTag,
      serviceInfo.groups,
      removedEndpointKeySet,
    );
    if (nextEndpoint) {
      const matchedTag = Object.entries(endpointsByTag).find(([, endpoints]) =>
        endpoints.some((item) => item.id === nextEndpoint.id),
      )?.[0];
      if (matchedTag) {
        setExpandedKeys((prev) =>
          prev.includes(`group:${matchedTag}`) ? prev : [...prev, `group:${matchedTag}`],
        );
      }
      void loadEndpointDetail(selectedServiceId, nextEndpoint.id);
      return;
    }
    setSelectedEndpoint(null);
  }, [
    detailTab,
    endpointsByTag,
    loadEndpointDetail,
    removedEndpointKeySet,
    selectedServiceId,
    serviceInfo?.groups,
  ]);

  const treeData = useMemo<DataNode[]>(() => {
    if (!serviceInfo?.groups.length) {
      return [];
    }
    const hasKeyword = Boolean(keyword.trim());
    return serviceInfo.groups
      .map((group) => {
        const endpoints = filterEndpointSummaries(treeEndpointsByTag[group.tag] ?? [], keyword);
        return {
          key: `group:${group.tag}`,
          title: `${group.tag} (${endpoints.length})`,
          selectable: false,
          children: endpoints.map((endpoint) => ({
            key: buildEndpointTreeKey(group.tag, endpoint.id),
            isLeaf: true,
            title: (
              <div className="api-monitor-page__tree-item">
                <MethodBadge method={endpoint.method} />
                <span className="api-monitor-page__tree-text">{endpoint.summary || endpoint.path}</span>
              </div>
            ),
          })),
        };
      })
      .filter((group) => !hasKeyword || (group.children?.length ?? 0) > 0);
  }, [keyword, serviceInfo?.groups, treeEndpointsByTag]);

  const selectedTreeKeys = useMemo(
    () => findSelectedTreeKeys(treeData, selectedEndpoint?.id),
    [selectedEndpoint?.id, treeData],
  );

  const selectedNameLabel = useMemo(() => {
    if (!selectedServiceId) {
      return '';
    }
    return (
      filterOptions.names.find((item) => item.id === selectedServiceId)?.label ||
      serviceInfo?.display_name ||
      selectedServiceId
    );
  }, [filterOptions.names, selectedServiceId, serviceInfo?.display_name]);

  const selectedProjectLabel = useMemo(() => {
    return filterOptions.projects.find((item) => item.id === selectedProjectId)?.name || '';
  }, [filterOptions.projects, selectedProjectId]);

  const selectedEnvironmentLabel = useMemo(() => {
    return filterOptions.environments.find((item) => item.id === selectedEnvironmentId)?.name || '';
  }, [filterOptions.environments, selectedEnvironmentId]);

  const selectedModuleSummary = useMemo(
    () => modules.find((item) => item.name === selectedModule),
    [modules, selectedModule],
  );

  const filterSummaryText = useMemo(() => {
    const parts = [
      selectedProjectLabel,
      selectedEnvironmentLabel,
      selectedNameLabel,
      selectedModule
        ? `${selectedModule}${selectedModuleSummary ? ` (${selectedModuleSummary.endpoint_count})` : ''}`
        : '',
    ].filter(Boolean);
    return parts.join(' · ') || '未选择筛选条件';
  }, [
    selectedEnvironmentLabel,
    selectedModule,
    selectedModuleSummary,
    selectedNameLabel,
    selectedProjectLabel,
  ]);

  const toggleFiltersExpanded = () => {
    setFiltersExpanded((prev) => {
      const next = !prev;
      localStorage.setItem(FILTER_PANEL_STORAGE_KEY, String(next));
      return next;
    });
  };

  const pageLoading = filterLoading || modulesLoading || groupsLoading || endpointLoading;
  const hasLoadedEndpoints = Object.keys(endpointsByTag).length > 0;

  return (
    <div
      className={`api-monitor-page${sidebarExpanded ? '' : ' api-monitor-page--sidebar-collapsed'}${filtersExpanded ? '' : ' api-monitor-page--filters-collapsed'}`}
    >
      <aside className="api-monitor-page__sidebar">
        <div className="api-monitor-page__sidebar-head">
          <Space size={8} align="center">
            <Typography.Text strong>接口监听</Typography.Text>
            <Button
              type="link"
              size="small"
              icon={<SettingOutlined />}
              className="api-monitor-page__env-preset-btn"
              onClick={() => setEnvPresetOpen(true)}
            >
              环境预置
            </Button>
          </Space>
          <Space size={4}>
            <Button
              type="text"
              size="small"
              icon={<ReloadOutlined />}
              loading={pageLoading}
              onClick={() => {
                bootstrapPage().catch(() => undefined);
              }}
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

        <div className="api-monitor-page__filter-panel">
          <button
            type="button"
            className="api-monitor-page__filter-toggle"
            onClick={toggleFiltersExpanded}
            title={filtersExpanded ? '收起筛选' : '展开筛选'}
          >
            <span className="api-monitor-page__filter-toggle-label">
              {filtersExpanded ? <CaretDownOutlined /> : <CaretRightOutlined />}
              <span>筛选条件</span>
            </span>
            <span className="api-monitor-page__filter-toggle-action">
              {filtersExpanded ? '收起' : '展开'}
            </span>
          </button>

          <div
            className={`api-monitor-page__filter-body${filtersExpanded ? '' : ' is-collapsed'}`}
            aria-hidden={!filtersExpanded}
          >
            <Form
              form={filterForm}
              layout="vertical"
              className="api-monitor-page__filters"
              onValuesChange={(changed) => {
                handleFilterChange(changed).catch(() => undefined);
              }}
            >
              <Form.Item name="project" label="项目">
                <Select
                  placeholder={filterOptions.projects.length ? '选择项目' : '暂无可用项目'}
                  loading={filterLoading}
                  options={filterOptions.projects.map((item) => ({
                    value: item.id,
                    label: item.name,
                  }))}
                />
              </Form.Item>
              <Form.Item name="environment" label="环境">
                <Select
                  placeholder={filterOptions.environments.length ? '选择环境' : '暂无可用环境'}
                  loading={filterLoading}
                  options={filterOptions.environments.map((item) => ({
                    value: item.id,
                    label: item.name,
                  }))}
                />
              </Form.Item>
              <Form.Item name="name" label="名称">
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder={filterOptions.names.length ? '选择名称' : '暂无可用名称'}
                  loading={filterLoading}
                  options={filterOptions.names.map((item) => ({
                    value: item.id,
                    label: item.label,
                  }))}
                />
              </Form.Item>
            </Form>

            <div className="api-monitor-page__service-switch">
              <Typography.Text type="secondary" className="api-monitor-page__service-label">
                服务
              </Typography.Text>
              <Select
                showSearch
                optionFilterProp="label"
                placeholder={modules.length ? '选择服务' : '暂无可用服务'}
                loading={modulesLoading || groupsLoading}
                value={selectedModule ?? undefined}
                onChange={(value) => {
                  handleModuleChange(value).catch(() => undefined);
                }}
                options={modules.map((item) => ({
                  value: item.name,
                  label: `${item.name} (${item.endpoint_count})`,
                }))}
                style={{ width: '100%' }}
              />
              {serviceInfo ? (
                <div className="api-monitor-page__service-meta">
                  <Typography.Text type="secondary" ellipsis>
                    {selectedNameLabel}
                  </Typography.Text>
                  <Typography.Text type="secondary" ellipsis>
                    {serviceInfo.project_display} · {serviceInfo.environment_display}
                  </Typography.Text>
                  <Typography.Text type="secondary" ellipsis>
                    {serviceInfo.repo_path}
                  </Typography.Text>
                  {serviceInfo.branch ? <Tag>{serviceInfo.branch}</Tag> : null}
                  {serviceInfo.scan_status === 'running' ? (
                    <Tag color="processing">生成中</Tag>
                  ) : serviceInfo.has_snapshot ? (
                    <Tag color="blue">{serviceInfo.endpoint_count} 个接口</Tag>
                  ) : (
                    <Tag>未生成</Tag>
                  )}
                </div>
              ) : null}
            </div>
          </div>

          {!filtersExpanded ? (
            <div className="api-monitor-page__filter-summary">
              <Typography.Text type="secondary" ellipsis={{ tooltip: filterSummaryText }}>
                {filterSummaryText}
              </Typography.Text>
            </div>
          ) : null}
        </div>

        <div className="api-monitor-page__search">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索当前服务下的接口"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
        </div>

        <div className="api-monitor-page__tree-wrap">
          {groupsLoading && !hasLoadedEndpoints ? (
            <div className="api-monitor-page__tree-loading">
              <Spin tip="加载接口列表...">
                <div style={{ minHeight: 48 }} />
              </Spin>
            </div>
          ) : treeData.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                filterOptions.projects.length === 0
                  ? '请先在日志订阅中启用链接，并配置 Clone 地址'
                  : serviceInfo?.scan_status === 'running' && !serviceInfo?.has_snapshot
                    ? '接口文档正在后台生成，请稍后刷新'
                    : !selectedModule
                      ? '请先选择服务'
                      : keyword.trim()
                        ? '当前服务下暂无匹配接口'
                        : detailTab === 'cases'
                          ? '当前服务下暂无未删除接口'
                          : '当前服务下暂无接口分类'
              }
            />
          ) : (
            <Tree
              treeData={treeData}
              expandedKeys={expandedKeys}
              onExpand={(keys) => {
                setExpandedKeys(keys as string[]);
              }}
              selectedKeys={selectedTreeKeys}
              onSelect={(keys) => {
                const raw = keys[0];
                const serviceId =
                  selectedServiceId || (filterForm.getFieldValue('name') as string | undefined);
                if (typeof raw === 'string' && !raw.startsWith('group:') && serviceId) {
                  loadEndpointDetail(serviceId, parseEndpointIdFromTreeKey(raw)).catch(() => undefined);
                }
              }}
            />
          )}
        </div>
      </aside>

      <section
        className={`api-monitor-page__main${
          selectedEndpoint || !sidebarExpanded ? ' api-monitor-page__main--with-rail' : ''
        }`}
      >
        {selectedEndpoint || !sidebarExpanded ? (
          <div className="api-monitor-page__main-rail">
            {!sidebarExpanded ? (
              <Button
                type="text"
                className="api-monitor-page__sidebar-expand"
                icon={<MenuUnfoldOutlined />}
                title="展开列表"
                onClick={() => setSidebarExpanded(true)}
              />
            ) : null}
            {selectedEndpoint ? (
              <>
                <button
                  type="button"
                  className={`api-monitor-page__main-tab${detailTab === 'doc' ? ' is-active' : ''}`}
                  onClick={() => setDetailTab('doc')}
                >
                  <FileTextOutlined />
                  <span>文档</span>
                </button>
                <button
                  type="button"
                  className={`api-monitor-page__main-tab${detailTab === 'cases' ? ' is-active' : ''}`}
                  onClick={() => setDetailTab('cases')}
                >
                  <ExperimentOutlined />
                  <span>用例生成</span>
                </button>
                <button
                  type="button"
                  className={`api-monitor-page__main-tab${detailTab === 'debug' ? ' is-active' : ''}`}
                  onClick={() => setDetailTab('debug')}
                >
                  <PlayCircleOutlined />
                  <span>调试</span>
                </button>
                <button
                  type="button"
                  className={`api-monitor-page__main-tab${detailTab === 'changes' ? ' is-active' : ''}`}
                  onClick={() => setDetailTab('changes')}
                >
                  <HistoryOutlined />
                  <span>变更</span>
                </button>
              </>
            ) : null}
          </div>
        ) : null}
        {endpointLoading && !selectedEndpoint ? (
          <div className="api-monitor-page__placeholder">
            <Spin tip="加载接口详情...">
              <div style={{ minHeight: 48 }} />
            </Spin>
          </div>
        ) : selectedEndpoint ? (
          <>
            {serviceInfo?.scan_status === 'running' ? (
              <div className="api-monitor-page__scan-banner">
                <Tag color="processing">更新中</Tag>
                <Typography.Text type="secondary">
                  正在后台拉取最新代码并生成文档，当前展示的是上次扫描结果
                </Typography.Text>
              </div>
            ) : null}
            <div className="api-monitor-page__main-body">
              {detailTab === 'doc' ? (
                <ApiMonitorDocPanel endpoint={selectedEndpoint} />
              ) : detailTab === 'cases' ? (
                <ApiMonitorCasesPanel
                  endpoint={selectedEndpoint}
                  projectId={selectedProjectId}
                  environmentId={selectedEnvironmentId}
                  service={selectedModule}
                  envPreset={envPreset}
                  projectOptions={projects.options}
                  environmentOptions={environments.options}
                />
              ) : detailTab === 'debug' ? (
                <ApiMonitorDebugPanel endpoint={selectedEndpoint} envPreset={envPreset} />
              ) : selectedServiceId ? (
                <ApiMonitorChangePanel serviceId={selectedServiceId} endpoint={selectedEndpoint} />
              ) : (
                <Empty description="请先选择服务" />
              )}
            </div>
          </>
        ) : (
          <div className="api-monitor-page__placeholder">
            <Empty
              description={
                filterOptions.projects.length === 0
                  ? '暂无已启用且配置 Clone 地址的服务'
                  : '请选择筛选条件后查看接口'
              }
            />
          </div>
        )}
      </section>

      <ApiMonitorEnvPresetModal
        open={envPresetOpen}
        preset={envPreset}
        onClose={() => setEnvPresetOpen(false)}
        onSaved={setEnvPreset}
      />
    </div>
  );
}
