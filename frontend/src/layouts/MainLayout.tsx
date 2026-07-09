import {
  ApiOutlined,
  AuditOutlined,
  BellOutlined,
  BookOutlined,
  CloudServerOutlined,
  CodeOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  HomeOutlined,
  LinkOutlined,
  LogoutOutlined,
  MessageOutlined,
  RadarChartOutlined,
  RobotOutlined,
  FileTextOutlined,
  SettingOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { Button, Layout, Menu, Space, Tabs, Typography } from 'antd';
import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { reportPageOpen } from '../api';
import { useAuth } from '../contexts/AuthContext';
import ConnectionMethodMqttPage from '../pages/connection-methods/ConnectionMethodMqttPage';
import KafkaMethodPage from '../pages/connection-methods/KafkaMethodPage';
import OmnidbMethodPage from '../pages/connection-methods/OmnidbMethodPage';
import RedisMethodPage from '../pages/connection-methods/RedisMethodPage';
import TerminalMethodPage from '../pages/connection-methods/TerminalMethodPage';
import ConnectionsPage from '../pages/ConnectionsPage';
import DictPage from '../pages/DictPage';
import HomePage from '../pages/HomePage';
import LogsPage from '../pages/LogsPage';
import ApiMonitorPage from '../pages/ApiMonitorPage';
import ApiCasePage from '../pages/ApiCasePage';
import ServiceMonitorPage from '../pages/ServiceMonitorPage';
import LlmConfigPage from '../pages/LlmConfigPage';
import PromptManagePage from '../pages/PromptManagePage';
import OperationLogPage from '../pages/OperationLogPage';
import UserManagePage from '../pages/UserManagePage';
import { hasMenuPermission } from '../types/auth';
import { canAccessConnectionsPage } from '../utils/connectionPermissions';
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
import WorkspaceSelector from '../components/WorkspaceSelector';
import { clearK8sConnectionSession } from '../utils/k8sConnectionSession';

const { Header, Sider, Content } = Layout;

function buildMenuItems(user: ReturnType<typeof useAuth>['user']): MenuProps['items'] {
  const items: NonNullable<MenuProps['items']> = [];
  const pushLeaf = (key: PageType, icon: ReactNode) => {
    if (hasMenuPermission(user, key)) {
      items.push({ key, icon, label: PAGE_LABELS[key] });
    }
  };

  pushLeaf('home', <HomeOutlined />);
  pushLeaf('logs', <BellOutlined />);
  pushLeaf('apiMonitor', <RadarChartOutlined />);
  pushLeaf('serviceMonitor', <CloudServerOutlined />);
  if (canAccessConnectionsPage(user)) {
    items.push({ key: 'connections', icon: <LinkOutlined />, label: PAGE_LABELS.connections });
  }
  pushLeaf('apiCases', <ExperimentOutlined />);

  const configChildren: NonNullable<MenuProps['items']> = [];
  const configDefs: Array<{ key: PageType; icon: ReactNode }> = [
    { key: 'llmConfigs', icon: <RobotOutlined /> },
    { key: 'prompts', icon: <FileTextOutlined /> },
    { key: 'dict', icon: <BookOutlined /> },
    { key: 'userManagement', icon: <TeamOutlined /> },
  ];
  for (const item of configDefs) {
    if (hasMenuPermission(user, item.key)) {
      configChildren.push({ key: item.key, icon: item.icon, label: PAGE_LABELS[item.key] });
    }
  }
  if (configChildren.length > 0) {
    items.push({
      key: CONFIG_MENU_KEY,
      icon: <SettingOutlined />,
      label: '配置管理',
      children: configChildren,
    });
  }

  const methodChildren: NonNullable<MenuProps['items']> = [];
  const methodDefs: Array<{ key: PageType; icon: ReactNode }> = [
    { key: 'methodDatabase', icon: <DatabaseOutlined /> },
    { key: 'methodTerminal', icon: <CodeOutlined /> },
    { key: 'methodRedis', icon: <CloudServerOutlined /> },
    { key: 'methodMqtt', icon: <MessageOutlined /> },
    { key: 'methodKafka', icon: <ApiOutlined /> },
  ];
  for (const item of methodDefs) {
    if (hasMenuPermission(user, item.key)) {
      methodChildren.push({ key: item.key, icon: item.icon, label: PAGE_LABELS[item.key] });
    }
  }
  if (methodChildren.length > 0) {
    items.push({
      key: CONNECTION_METHOD_MENU_KEY,
      icon: <ApiOutlined />,
      label: '连接方式',
      children: methodChildren,
    });
  }

  if (hasMenuPermission(user, 'operationLogs')) {
    items.push({
      key: 'operationLogs',
      icon: <AuditOutlined />,
      label: PAGE_LABELS.operationLogs,
    });
  }

  return items;
}

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
    case 'serviceMonitor':
      return <ServiceMonitorPage />;
    case 'apiCases':
      return <ApiCasePage />;
    case 'llmConfigs':
      return <LlmConfigPage />;
    case 'prompts':
      return <PromptManagePage />;
    case 'dict':
      return <DictPage />;
    case 'userManagement':
      return <UserManagePage />;
    case 'operationLogs':
      return <OperationLogPage />;
    case 'methodDatabase':
      return <OmnidbMethodPage />;
    case 'methodTerminal':
      return <TerminalMethodPage />;
    case 'methodRedis':
      return <RedisMethodPage />;
    case 'methodMqtt':
      return <ConnectionMethodMqttPage />;
    case 'methodKafka':
      return <KafkaMethodPage />;
    default:
      return null;
  }
}

export default function MainLayout() {
  const { user, logout } = useAuth();
  const [tabs, setTabs] = useState<AppTab[]>(() => [createTab('home')]);
  const [activeKey, setActiveKey] = useState<PageType>('home');
  const [menuOpenKeys, setMenuOpenKeys] = useState<string[]>([]);

  const menuItems = useMemo(() => buildMenuItems(user), [user]);

  const openTab = useCallback(
    (type: PageType) => {
      if (!hasMenuPermission(user, type)) {
        return;
      }
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
    },
    [user],
  );

  const closeTab = useCallback(
    (targetKey: string) => {
      const type = targetKey as PageType;
      if (type === 'serviceMonitor') {
        clearK8sConnectionSession();
      }
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

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === CONNECTION_METHOD_MENU_KEY || key === CONFIG_MENU_KEY) return;
    const pageKey = key as PageType;
    if (!hasMenuPermission(user, pageKey)) return;
    void reportPageOpen(pageKey).catch(() => undefined);
    openTab(pageKey);
  };

  return (
    <Layout className="app-shell">
      <Header className="app-header">
        <Typography.Title level={4} style={{ margin: 0, color: '#fff' }}>
          QuickNavigation
        </Typography.Title>
        <Space align="center" size={16} className="app-header__actions">
          <WorkspaceSelector />
          <Typography.Text className="app-header__user">
            {user?.nickname || user?.username}
          </Typography.Text>
          <Button
            type="text"
            icon={<LogoutOutlined />}
            className="app-header__logout"
            onClick={() => void logout()}
          >
            退出
          </Button>
        </Space>
      </Header>

      <Layout className="app-body">
        <Sider width={200} className="app-sider" theme="light">
          <Menu
            mode="inline"
            selectedKeys={selectedMenuKeys}
            openKeys={menuOpenKeys}
            onOpenChange={setMenuOpenKeys}
            items={menuItems}
            onClick={handleMenuClick}
          />
        </Sider>

        <Layout className="app-main">
          <Content className={`app-content${activeTabType === 'home' ? ' app-content--home' : ''}`}>
            <Tabs
              className={`app-tabs${activeTabType === 'home' ? ' app-tabs--home' : ''}${
                activeTabType === 'serviceMonitor' ? ' app-tabs--service-monitor' : ''
              }`}
              type="editable-card"
              hideAdd
              destroyInactiveTabPane
              animated={{ inkBar: true, tabPane: false }}
              activeKey={activeKey}
              onChange={(key) => setActiveKey(key as PageType)}
              onEdit={(targetKey, action) => {
                if (action === 'remove' && typeof targetKey === 'string') {
                  closeTab(targetKey);
                }
              }}
              items={tabItems}
            />
          </Content>
        </Layout>
      </Layout>
    </Layout>
  );
}
