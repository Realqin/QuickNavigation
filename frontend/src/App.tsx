import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Spin } from 'antd';
import MqttConsolePage from './features/mqtt-console/MqttConsolePage';
import EmbedSessionPage from './pages/EmbedSessionPage';
import LoginPage from './pages/LoginPage';
import MainLayout from './layouts/MainLayout';
import { useAuth } from './contexts/AuthContext';

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return <Spin fullscreen tip="加载中..." />;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/embed/session/:sessionId"
          element={
            <RequireAuth>
              <EmbedSessionPage />
            </RequireAuth>
          }
        />
        <Route
          path="/mqtt"
          element={
            <RequireAuth>
              <MqttConsolePage />
            </RequireAuth>
          }
        />
        <Route
          path="/"
          element={
            <RequireAuth>
              <MainLayout />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
