import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const kafkaProvider = (env.VITE_KAFKA_CONSOLE_PROVIDER || env.KAFKA_CONSOLE_PROVIDER || 'redpanda').toLowerCase();

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      hmr: {
        host: '127.0.0.1',
        port: 5173,
      },
      proxy: {
        '/api': 'http://127.0.0.1:8000',
        '/webhooks': 'http://127.0.0.1:8000',
        '/ws': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          ws: true,
          secure: false,
        },
        '/proxy/kafka': {
          target: 'http://127.0.0.1:8082',
          changeOrigin: true,
          ws: true,
          rewrite: (path) => {
            if (kafkaProvider === 'kafka-ui') {
              return path;
            }
            return path.replace(/^\/proxy\/kafka\/?/, '/') || '/';
          },
        },
      },
    },
  };
});