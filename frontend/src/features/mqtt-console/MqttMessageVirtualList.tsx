import { Empty } from 'antd';
import MqttMessageListItem from './MqttMessageListItem';
import type { MqttMessageRecord } from './types';

interface Props {
  messages: MqttMessageRecord[];
  selectedTopic?: string | null;
}

export default function MqttMessageVirtualList({ messages, selectedTopic }: Props) {
  if (messages.length === 0) {
    return (
      <div className="mqtt-console__message-panel">
        <Empty
          description={
            selectedTopic ? `暂无「${selectedTopic}」相关消息` : '暂无消息'
          }
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </div>
    );
  }

  return (
    <div className="mqtt-console__message-panel">
      <div className="mqtt-console__message-list">
        {messages.map((item) => (
          <MqttMessageListItem key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
