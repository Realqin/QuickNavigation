import {
  ApiOutlined,
  BugOutlined,
  CloudOutlined,
  CodeOutlined,
  DatabaseOutlined,
  GithubOutlined,
  GlobalOutlined,
  LinkOutlined,
  MonitorOutlined,
  RocketOutlined,
  SafetyOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import type { ComponentType } from 'react';
import type { Connection, DictItem } from '../types';

export const LABEL_COLORS = [
  'blue',
  'purple',
  'green',
  'orange',
  'cyan',
  'magenta',
  'gold',
  'geekblue',
  'volcano',
  'lime',
] as const;

export type LabelColorKey = (typeof LABEL_COLORS)[number];

export const LABEL_TEXT_COLORS: Record<LabelColorKey | string, string> = {
  blue: '#1677ff',
  purple: '#722ed1',
  green: '#52c41a',
  orange: '#fa8c16',
  cyan: '#13c2c2',
  magenta: '#eb2f96',
  gold: '#faad14',
  geekblue: '#2f54eb',
  volcano: '#fa541c',
  lime: '#a0d911',
};

export const LABEL_ICON_COMPONENTS: ComponentType<{ style?: React.CSSProperties }>[] = [
  GlobalOutlined,
  ApiOutlined,
  CloudOutlined,
  MonitorOutlined,
  DatabaseOutlined,
  GithubOutlined,
  RocketOutlined,
  ToolOutlined,
  CodeOutlined,
  LinkOutlined,
  BugOutlined,
  SafetyOutlined,
];

function sortedDictItems(items: DictItem[]) {
  return [...items].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
}

export function buildLabelColorMap(items: DictItem[]): Record<number, LabelColorKey> {
  return Object.fromEntries(
    sortedDictItems(items).map((item, index) => [
      item.id,
      LABEL_COLORS[index % LABEL_COLORS.length],
    ]),
  ) as Record<number, LabelColorKey>;
}

export function buildLabelOrderMap(items: DictItem[]): Record<number, number> {
  return Object.fromEntries(sortedDictItems(items).map((item, index) => [item.id, index]));
}

export function buildLabelIconIndexMap(items: DictItem[]): Record<number, number> {
  return Object.fromEntries(
    sortedDictItems(items).map((item, index) => [item.id, index % LABEL_ICON_COMPONENTS.length]),
  );
}

export function sortConnectionsByTypeOrder(
  connections: Connection[],
  labelOrderMap: Record<number, number>,
): Connection[] {
  return [...connections].sort((a, b) => {
    const orderA = labelOrderMap[a.type] ?? Number.MAX_SAFE_INTEGER;
    const orderB = labelOrderMap[b.type] ?? Number.MAX_SAFE_INTEGER;
    if (orderA !== orderB) return orderA - orderB;
    return a.sort_order - b.sort_order || a.id - b.id;
  });
}

export function getTypeTextColor(colorKey?: string): string {
  if (!colorKey) return LABEL_TEXT_COLORS.blue;
  return LABEL_TEXT_COLORS[colorKey] ?? LABEL_TEXT_COLORS.blue;
}

export function hexWithAlpha(hex: string, alpha: number): string {
  const normalized = hex.replace('#', '');
  if (normalized.length !== 6) return hex;
  const r = parseInt(normalized.slice(0, 2), 16);
  const g = parseInt(normalized.slice(2, 4), 16);
  const b = parseInt(normalized.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function matchKeywordIcon(typeName: string): ComponentType<{ style?: React.CSSProperties }> | null {
  const key = typeName.toLowerCase();
  if (key.includes('github')) return GithubOutlined;
  if (key.includes('gitlab')) return CodeOutlined;
  if (key.includes('数据库') || key.includes('database') || key.includes('db')) return DatabaseOutlined;
  if (key.includes('api') || key.includes('接口')) return ApiOutlined;
  if (key.includes('监控') || key.includes('grafana') || key.includes('monitor')) return MonitorOutlined;
  if (key.includes('云') || key.includes('cloud')) return CloudOutlined;
  if (key.includes('wiki') || key.includes('文档') || key.includes('doc')) return LinkOutlined;
  if (key.includes('代码') || key.includes('code') || key.includes('git')) return CodeOutlined;
  if (key.includes('安全') || key.includes('security')) return SafetyOutlined;
  if (key.includes('测试') || key.includes('test') || key.includes('bug')) return BugOutlined;
  if (key.includes('工具') || key.includes('tool')) return ToolOutlined;
  if (key.includes('部署') || key.includes('deploy') || key.includes('rocket')) return RocketOutlined;
  return null;
}

export function resolveTypeIcon(
  typeName: string | undefined,
  iconIndex: number,
): ComponentType<{ style?: React.CSSProperties }> {
  const matched = typeName ? matchKeywordIcon(typeName) : null;
  if (matched) return matched;
  return LABEL_ICON_COMPONENTS[iconIndex % LABEL_ICON_COMPONENTS.length] ?? GlobalOutlined;
}
