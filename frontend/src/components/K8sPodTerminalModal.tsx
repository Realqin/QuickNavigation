import { Modal, Typography } from 'antd';
import { FitAddon } from '@xterm/addon-fit';
import { Terminal } from '@xterm/xterm';
import { useEffect, useState } from 'react';
import { buildK8sExecWebSocketUrl } from '../utils/k8sExec';
import '@xterm/xterm/css/xterm.css';

export interface K8sPodTerminalTarget {
  namespace: string;
  podName: string;
  container?: string;
}

interface K8sPodTerminalModalProps {
  open: boolean;
  clusterId: number | null;
  target: K8sPodTerminalTarget | null;
  onClose: () => void;
}

export default function K8sPodTerminalModal({
  open,
  clusterId,
  target,
  onClose,
}: K8sPodTerminalModalProps) {
  const [terminalHost, setTerminalHost] = useState<HTMLDivElement | null>(null);
  const [statusText, setStatusText] = useState('正在连接终端...');

  useEffect(() => {
    if (!open) {
      setTerminalHost(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open || !clusterId || !target || !terminalHost) {
      return;
    }

    const terminal = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace",
      theme: {
        background: '#0f172a',
        foreground: '#e2e8f0',
        cursor: '#38bdf8',
      },
      convertEol: true,
    });
    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.open(terminalHost);
    fitAddon.fit();

    let disposed = false;
    let socket: WebSocket | null = null;
    let resizeObserver: ResizeObserver | null = null;

    const sendResize = () => {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        return;
      }
      fitAddon.fit();
      socket.send(
        JSON.stringify({
          type: 'resize',
          cols: terminal.cols,
          rows: terminal.rows,
        }),
      );
    };

    const wsUrl = buildK8sExecWebSocketUrl({
      clusterId,
      namespace: target.namespace,
      podName: target.podName,
      container: target.container,
    });
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      if (disposed) {
        return;
      }
      setStatusText('终端已连接，可输入命令查看日志');
      terminal.focus();
      sendResize();
    };

    socket.onmessage = (event) => {
      if (disposed) {
        return;
      }
      try {
        const payload = JSON.parse(String(event.data)) as {
          type?: string;
          data?: string;
          message?: string;
          status?: string;
        };
        if (payload.type === 'output' && payload.data) {
          terminal.write(payload.data);
          return;
        }
        if (payload.type === 'error' && payload.message) {
          terminal.writeln(`\r\n\x1b[31m${payload.message}\x1b[0m`);
          setStatusText(payload.message);
          return;
        }
        if (payload.type === 'status') {
          if (payload.status === 'connected') {
            setStatusText('终端已连接，可输入命令查看日志');
            return;
          }
          if (payload.status === 'error' && payload.message) {
            terminal.writeln(`\r\n\x1b[31m${payload.message}\x1b[0m`);
            setStatusText(payload.message);
          }
        }
      } catch {
        terminal.write(String(event.data));
      }
    };

    socket.onerror = () => {
      if (!disposed) {
        setStatusText('终端连接失败');
        terminal.writeln('\r\n\x1b[31m终端连接失败\x1b[0m');
      }
    };

    socket.onclose = () => {
      if (!disposed) {
        setStatusText('终端连接已断开');
        terminal.writeln('\r\n\x1b[33m终端连接已断开\x1b[0m');
      }
    };

    const dataDisposable = terminal.onData((data) => {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        return;
      }
      socket.send(JSON.stringify({ type: 'input', data }));
    });

    resizeObserver = new ResizeObserver(() => {
      sendResize();
    });
    resizeObserver.observe(terminalHost);
    window.addEventListener('resize', sendResize);

    return () => {
      disposed = true;
      dataDisposable.dispose();
      window.removeEventListener('resize', sendResize);
      resizeObserver?.disconnect();
      socket?.close();
      terminal.dispose();
      setStatusText('正在连接终端...');
    };
  }, [open, clusterId, target, terminalHost]);

  const title = target
    ? `容器终端 / ${target.podName}${target.container ? ` / ${target.container}` : ''}`
    : '容器终端';

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onClose}
      footer={null}
      width={1080}
      destroyOnHidden
      className="k8s-pod-terminal-modal"
    >
      <Typography.Text type="secondary" className="k8s-pod-terminal-modal__status">
        {statusText}
      </Typography.Text>
      <div ref={setTerminalHost} className="k8s-pod-terminal-modal__terminal" />
    </Modal>
  );
}
