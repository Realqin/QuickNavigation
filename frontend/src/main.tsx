import React from 'react';
import ReactDOM from 'react-dom/client';
import { App as AntdApp, ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import './styles/global.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: { colorPrimary: '#1677ff', borderRadius: 8 },
      }}
      tooltip={{
        styles: {
          root: { maxWidth: 'min(480px, calc(100vw - 32px))' },
          body: {
            maxHeight: 'min(420px, calc(100vh - 32px))',
            overflowX: 'hidden',
            overflowY: 'auto',
            wordBreak: 'break-word',
          },
        },
      }}
      popover={{
        styles: {
          root: { maxWidth: 'min(480px, calc(100vw - 32px))' },
          body: {
            maxHeight: 'min(420px, calc(100vh - 32px))',
            overflowX: 'hidden',
            overflowY: 'auto',
            wordBreak: 'break-word',
          },
        },
      }}
    >
      <AntdApp>
        <App />
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>,
);
