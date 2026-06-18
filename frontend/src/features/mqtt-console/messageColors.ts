/** 消息轮播浅色底（淡淡底色） */
export const MESSAGE_BG_COLORS = [
  '#f6ffed',
  '#e6f4ff',
  '#fff7e6',
  '#f9f0ff',
  '#e6fffb',
  '#fcffe6',
  '#fff0f6',
  '#f0f5ff',
  '#fafafa',
  '#fffbe6',
] as const;

export function nextMessageColorIndex(current: number): number {
  return (current + 1) % MESSAGE_BG_COLORS.length;
}
