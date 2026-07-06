import { Typography } from 'antd';
import { memo } from 'react';
import type { MqttMessageRecord } from './types';

interface Props {
  item: MqttMessageRecord;
}

function MqttMessageListItem({ item }: Props) {
  return (
    <div className="mqtt-console__message-item">
      <div className="mqtt-console__message-meta">
        <div className="mqtt-console__message-meta-main">
          <Typography.Text
            code
            className="mqtt-console__message-topic"
            ellipsis={{ tooltip: item.topic }}
          >
            {item.topic}
          </Typography.Text>
          {item.code ? (
            <Typography.Text className="mqtt-console__message-code">
              code: {item.code}
            </Typography.Text>
          ) : null}
        </div>
        <Typography.Text type="secondary" className="mqtt-console__message-time">
          {item.receivedAt}
        </Typography.Text>
      </div>
      <pre
        className="mqtt-console__message-payload"
        style={{
          background: item.backgroundColor,
        }}
      >
        {item.payload}
      </pre>
    </div>
  );
}

export default memo(MqttMessageListItem);
