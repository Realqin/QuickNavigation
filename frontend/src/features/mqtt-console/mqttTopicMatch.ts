/** MQTT 主题过滤匹配（支持 + 与 #） */
export function mqttTopicMatches(filter: string, topic: string): boolean {
  const filterParts = filter.split('/');
  const topicParts = topic.split('/');

  for (let i = 0; i < filterParts.length; i += 1) {
    const part = filterParts[i];
    if (part === '#') {
      return true;
    }
    if (i >= topicParts.length) {
      return false;
    }
    if (part === '+') {
      continue;
    }
    if (part !== topicParts[i]) {
      return false;
    }
  }

  return filterParts.length === topicParts.length;
}
