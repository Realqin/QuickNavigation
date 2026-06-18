import { Modal } from 'antd';
import ApiMonitorChangeCompareView from '../features/api-monitor/ApiMonitorChangeCompareView';
import type { ApiMonitorEndpointChange } from '../types/apiMonitor';
interface Props {
  change: ApiMonitorEndpointChange | null;
  open: boolean;
  onClose: () => void;
}

export default function ApiMonitorChangeCompareModal({ change, open, onClose }: Props) {
  return (
    <Modal
      title={change ? `接口变更对比 · ${change.endpoint_key}` : '接口变更对比'}
      open={open}
      onCancel={onClose}
      footer={null}
      width={1080}
      destroyOnHidden
      className="api-monitor-change-compare-modal"
    >
      {change ? <ApiMonitorChangeCompareView change={change} /> : null}
    </Modal>
  );
}
