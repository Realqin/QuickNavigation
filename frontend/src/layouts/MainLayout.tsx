import {
  ApiOutlined,
  BellOutlined,
  BookOutlined,
  CloudServerOutlined,
  CodeOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  HomeOutlined,
  LinkOutlined,
  MessageOutlined,
  RadarChartOutlined,
  RobotOutlined,
  FileTextOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { Layout, Menu, Tabs, Typography } from 'antd';
import { useCallback, useMemo, useState } from 'react';
import ConnectionMethodMqttPage from '../pages/connection-methods/ConnectionMethodMqttPage';
import EmbeddedConsolePage from '../pages/connection-methods/EmbeddedConsolePage';
import KafkaMethodPage from '../pages/connection-methods/KafkaMethodPage';
import OmnidbMethodPage from '../pages/connection-methods/OmnidbMethodPage';
import ConnectionsPage from '../pages/ConnectionsPage';
import DictPage from '../pages/DictPage';
import HomePage from '../pages/HomePage';
import LogsPage from '../pages/LogsPage';
import ApiMonitorPage from '../pages/ApiMonitorPage';
import ApiCasePage from '../pages/ApiCasePage';
import LlmConfigPage from '../pages/LlmConfigPage';
import PromptManagePage from '../pages/PromptManagePage';
import {
  CONNECTION_METHOD_MENU_KEY,
  CONFIG_MENU_KEY,
  createTab,
  isConfigPageType,
  isConnectionMethodType,
  PAGE_LABELS,
  type AppTab,
  type PageType,
} from '../types/tabs';

const { Header, Sider, Content } = Layout;

const MENU_ITEMS: MenuProps['items'] = [
  { key: 'home', icon: <HomeOutlined />, label: PAGE_LABELS.home },
  { key: 'connections', icon: <LinkOutlined />, label: PAGE_LABELS.connections },
  {
    key: CONNECTION_METHOD_MENU_KEY,
    icon: <ApiOutlined />,
    label: '连接方式',
    children: [
      { key: 'methodDatabase', icon: <DatabaseOutlined />, label: PAGE_LABELS.methodDatabase },
      { key: 'methodTerminal', icon: <CodeOutlined />, label: PAGE_LABELS.methodTerminal },
      { key: 'methodRedis', icon: <CloudServerOutlined />, label: PAGE_LABELS.methodRedis },
      { key: 'methodMqtt', icon: <MessageOutlined />, label: PAGE_LABELS.methodMqtt },
      { key: 'methodKafka', icon: <ApiOutlined />, label: PAGE_LABELS.methodKafka },
    ],
  },
  { key: 'logs', icon: <BellOutlined />, label: PAGE_LABELS.logs },
  { key: 'apiMonitor', icon: <RadarChartOutlined />, label: PAGE_LABELS.apiMonitor },
  { key: 'apiCases', icon: <ExperimentOutlined />, label: PAGE_LABELS.apiCases },
  {
    key: CONFIG_MENU_KEY,
    icon: <SettingOutlined />,
    label: '配置管理',
    children: [
      { key: 'llmConfigs', icon: <RobotOutlined />, label: PAGE_LABELS.llmConfigs },
      { key: 'prompts', icon: <FileTextOutlined />, label: PAGE_LABELS.prompts },
      { key: 'dict', icon: <BookOutlined />, label: PAGE_LABELS.dict },
    ],
  },
];

function renderTabContent(tab: AppTab) {
  switch (tab.type) {
    case 'home':
      return <HomePage />;
    case 'connections':
      return <ConnectionsPage />;
    case 'logs':
      return <LogsPage />;
    case 'apiMonitor':
      return <ApiMonitorPage />;
    case 'apiCases':
      return <ApiCasePage />;
    case 'llmConfigs':
      return <LlmConfigPage />;
    case 'prompts':
      return <PromptManagePage />;
    case 'dict':
      return <DictPage />;
    case 'methodDatabase':
      return <OmnidbMethodPage />;
    case 'methodTerminal':
      return (
        <EmbeddedConsolePage
          configKey="sshwifty_base_url"
          defaultPort={8182}
          emptyHint="无法加载终端控制台，请确认 Sshwifty 已启动（端口 8182）"
        />
      );
    case 'methodRedis':
      return (
        <EmbeddedConsolePage
          configKey="redisinsight_base_url"
          defaultPort={5540}
          emptyHint="无法加载 Redis 控制台，请确认 RedisInsight 已启动（端口 5540）"
        />
      );
    case 'methodMqtt':
      return <ConnectionMethodMqttPage />;
    case 'methodKafka':
      return <KafkaMethodPage />;
    default:
      return null;
  }
}

export default function MainLayout() {
  const [tabs, setTabs] = useState<AppTab[]>(() => [createTab('home')]);
  const [activeKey, setActiveKey] = useState<PageType>('home');
  const [menuOpenKeys, setMenuOpenKeys] = useState<string[]>([]);

  const openTab = useCallback((type: PageType) => {
    setTabs((prev) => {
      const existing = prev.find((t) => t.type === type);
      if (existing) {
        setActiveKey(type);
        return prev;
      }
      setActiveKey(type);
      return [...prev, createTab(type)];
    });
    if (isConnectionMethodType(type)) {
      setMenuOpenKeys((prev) =>
        prev.includes(CONNECTION_METHOD_MENU_KEY) ? prev : [...prev, CONNECTION_METHOD_MENU_KEY],
      );
    }
    if (isConfigPageType(type)) {
      setMenuOpenKeys((prev) =>
        prev.includes(CONFIG_MENU_KEY) ? prev : [...prev, CONFIG_MENU_KEY],
      );
    }
  }, []);

  const closeTab = useCallback(
    (targetKey: string) => {
      const type = targetKey as PageType;
      setTabs((prev) => {
        if (prev.length <= 1) return prev;
        const nextTabs = prev.filter((t) => t.key !== type);
        if (activeKey === type) {
          const closedIndex = prev.findIndex((t) => t.key === type);
          const nextActive = nextTabs[Math.min(closedIndex, nextTabs.length - 1)];
          setActiveKey(nextActive.key);
        }
        return nextTabs;
      });
    },
    [activeKey],
  );

  const activeTabType = useMemo(
    () => tabs.find((t) => t.key === activeKey)?.type ?? 'home',
    [tabs, activeKey],
  );

  const selectedMenuKeys = useMemo(() => {
    if (isConnectionMethodType(activeTabType)) {
      return [activeTabType];
    }
    return [activeTabType];
  }, [activeTabType]);

  const tabItems = useMemo(
    () =>
      tabs.map((tab) => ({
        key: tab.key,
        label: tab.label,
        closable: tabs.length > 1,
        children: (
          <div className="tab-pane-body" key={tab.key}>
            {renderTabContent(tab)}
          </div>
        ),
      })),
    [tabs],
  );

  return (
    <Layout className="app-shell">
      <Header className="app-header">
        <Typography.Title level={4} style={{ margin: 0, color: '#fff' }}>
          QuickNavigation
        </Typography.Title>
      </Header>

      <Layout className="app-body">
        <Sider width={200} className="app-sider" theme="light">
          <Menu
            mode="inline"
            selectedKeys={selectedMenuKeys}
            openKeys={menuOpenKeys}
            onOpenChange={setMenuOpenKeys}
            items={MENU_ITEMS}
            onClick={({ key }) => {
              if (key === CONNECTION_METHOD_MENU_KEY || key === CONFIG_MENU_KEY) return;
              openTab(key as PageType);
            }}
          />
        </Sider>

        <Layout className="app-main">
          <Content className={`app-content${activeTabType === 'home' ? ' app-content--home' : ''}`}>
            <Tabs
              className={`app-tabs${activeTabType === 'home' ? ' app-tabs--home' : ''}`}
              type="editable-card"
              hideAdd
              activeKey={activeKey}
              onChange={(key) => setActiveKey(key as PageType)}
              onEdit={(targetKey, action) => {
                if (action === 'remove' && typeof targetKey === 'string') {
                  closeTab(targetKey);
                }
              }}
              items={tabItems}
              destroyOnHidden
            />
          </Content>
        </Layout>
      </Layout>
    </Layout>
  );
}
