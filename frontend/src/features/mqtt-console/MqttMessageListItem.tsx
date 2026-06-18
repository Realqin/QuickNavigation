import { Typography } from 'antd';
import { memo } from 'react';
import { MESSAGE_BG_COLORS } from './messageColors';
import type { MqttMessageRecord } from './types';

interface Props {
  item: MqttMessageRecord;
}

function MqttMessageListItem({ item }: Props) {
  return (
    <div className="mqtt-console__message-item">
      <div className="mqtt-console__message-meta">
        <Typography.Text code>{item.topic}</Typography.Text>
        <Typography.Text type="secondary">{item.receivedAt}</Typography.Text>
      </div>
      <pre
        className="mqtt-console__message-payload"
        style={{
          background: MESSAGE_BG_COLORS[item.colorIndex % MESSAGE_BG_COLORS.length],
        }}
      >
        {item.payload}
      </pre>
    </div>
  );
}

export default memo(MqttMessageListItem);
