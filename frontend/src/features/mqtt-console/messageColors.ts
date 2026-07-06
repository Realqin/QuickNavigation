const CODE_COLOR_COUNT = 48;
const FALLBACK_MESSAGE_BG_COLORS = [
  '#f8fafc',
  '#f4f4f5',
  '#f5f5f4',
  '#fafaf9',
  '#f7fee7',
  '#f0fdfa',
  '#fff7ed',
  '#fdf2f8',
] as const;

export function getCodeMessageColor(index: number): string {
  const hue = Math.round((index * 137.508 + 18) % 360);
  const round = Math.floor(index / CODE_COLOR_COUNT);
  const saturation = round % 2 === 0 ? 86 : 70;
  const lightness = round % 2 === 0 ? 94 : 90;
  return `hsl(${hue} ${saturation}% ${lightness}%)`;
}

export function getRandomFallbackMessageColor(): string {
  const index = Math.floor(Math.random() * FALLBACK_MESSAGE_BG_COLORS.length);
  return FALLBACK_MESSAGE_BG_COLORS[index];
}
