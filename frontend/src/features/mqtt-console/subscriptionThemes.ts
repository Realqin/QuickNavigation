export interface SubscriptionTheme {
  accent: string;
  background: string;
}

export const SUBSCRIPTION_THEMES: SubscriptionTheme[] = [
  { accent: '#52c41a', background: '#f6ffed' },
  { accent: '#1677ff', background: '#e6f4ff' },
  { accent: '#d4a574', background: '#faf6f0' },
  { accent: '#389e0d', background: '#eef9e8' },
  { accent: '#722ed1', background: '#f9f0ff' },
  { accent: '#13c2c2', background: '#e6fffb' },
];

export function getSubscriptionTheme(index: number): SubscriptionTheme {
  return SUBSCRIPTION_THEMES[index % SUBSCRIPTION_THEMES.length];
}
