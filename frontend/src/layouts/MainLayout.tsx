import {
  BellOutlined,
  BookOutlined,
  HomeOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import { Layout, Menu, Tabs, Typography } from 'antd';
import { useCallback, useMemo, useState } from 'react';
import ConnectionsPage from '../pages/ConnectionsPage';
import DictPage from '../pages/DictPage';
import HomePage from '../pages/HomePage';
import LogsPage from '../pages/LogsPage';
import { createTab, PAGE_LABELS, type AppTab, type PageType } from '../types/tabs';

const { Header, Sider, Content } = Layout;

const MENU_ITEMS = [
  { key: 'home', icon: <HomeOutlined />, label: PAGE_LABELS.home },
  { key: 'connections', icon: <LinkOutlined />, label: PAGE_LABELS.connections },
  { key: 'logs', icon: <BellOutlined />, label: PAGE_LABELS.logs },
  { key: 'dict', icon: <BookOutlined />, label: PAGE_LABELS.dict },
];

function renderTabContent(tab: AppTab) {
  switch (tab.type) {
    case 'home':
      return <HomePage />;
    case 'connections':
      return <ConnectionsPage />;
    case 'logs':
      return <LogsPage />;
    case 'dict':
      return <DictPage />;
    default:
      return null;
  }
}

export default function MainLayout() {
  const [tabs, setTabs] = useState<AppTab[]>(() => [createTab('home')]);
  const [activeKey, setActiveKey] = useState<PageType>('home');

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
            selectedKeys={[activeTabType]}
            items={MENU_ITEMS}
            onClick={({ key }) => openTab(key as PageType)}
          />
        </Sider>

        <Layout className="app-main">
          <Content className="app-content">
            <Tabs
              className="app-tabs"
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
              destroyInactiveTabPane={false}
            />
          </Content>
        </Layout>
      </Layout>
    </Layout>
  );
}
