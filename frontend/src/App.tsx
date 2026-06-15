import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import MqttConsolePage from './features/mqtt-console/MqttConsolePage';
import EmbedSessionPage from './pages/EmbedSessionPage';
import MainLayout from './layouts/MainLayout';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/embed/session/:sessionId" element={<EmbedSessionPage />} />
        <Route path="/mqtt" element={<MqttConsolePage />} />
        <Route path="/" element={<MainLayout />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
