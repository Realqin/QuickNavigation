import type { ActivityLog } from '../types';

export interface SchemaChangeItem {
  operation: string;
  table?: string | null;
  summary: string;
  details?: string[];
  diff?: string[];
  before?: string | null;
  after?: string | null;
}

export interface SchemaChangeCompare {
  before: string;
  after: string;
  diff: string[];
}

const OPERATION_LABELS: Record<string, string> = {
  CREATE_DATABASE: '新增库',
  DROP_DATABASE: '删除库',
  CREATE_TABLE: '新增表',
  DROP_TABLE: '删除表',
  ALTER_TABLE: '修改表',
};

function normalizeChangeItem(item: Record<string, unknown>): SchemaChangeItem {
  const details = Array.isArray(item.details) ? item.details.map(String) : [];
  const diffRaw = Array.isArray(item.diff) ? item.diff.map(String) : details;
  return {
    operation: String(item.operation ?? ''),
    table: (item.table as string | null | undefined) ?? null,
    summary: String(item.summary ?? ''),
    details,
    diff: diffRaw,
    before: typeof item.before === 'string' ? item.before : null,
    after: typeof item.after === 'string' ? item.after : null,
  };
}

export function getSchemaChanges(log: ActivityLog): SchemaChangeItem[] {
  if (log.payload?.event !== 'schema_change') {
    return [];
  }
  if (Array.isArray(log.payload.changes) && log.payload.changes.length > 0) {
    return (log.payload.changes as Record<string, unknown>[]).map(normalizeChangeItem);
  }
  if (log.payload.operation) {
    const preview = log.payload.sql_preview;
    const details =
      typeof preview === 'string' && preview
        ? preview.split('; ').map((item) => item.trim()).filter(Boolean)
        : [];
    return [
      normalizeChangeItem({
        operation: log.payload.operation,
        table: (log.payload.table as string | null | undefined) ?? null,
        summary: String(log.summary ?? log.payload.operation),
        details,
        diff: details,
        before: typeof log.payload.before === 'string' ? log.payload.before : null,
        after: typeof log.payload.after === 'string' ? log.payload.after : null,
      }),
    ];
  }
  return [];
}

export function resolveSchemaChangeCompare(item: SchemaChangeItem): SchemaChangeCompare {
  const diff = item.diff?.length ? item.diff : item.details ?? [];
  if (item.before || item.after) {
    return {
      before: item.before || '（无）',
      after: item.after || '（无）',
      diff,
    };
  }

  switch (item.operation) {
    case 'CREATE_DATABASE':
    case 'CREATE_TABLE':
      return {
        before: '（不存在）',
        after: item.summary,
        diff: diff.length > 0 ? diff : [item.summary],
      };
    case 'DROP_DATABASE':
    case 'DROP_TABLE':
      return {
        before: item.summary,
        after: '（已删除）',
        diff: diff.length > 0 ? diff : [item.summary],
      };
    case 'ALTER_TABLE':
      return {
        before: '（历史记录未保存修改前快照）',
        after: '（历史记录未保存修改后快照）',
        diff,
      };
    default:
      return {
        before: '（无）',
        after: '（无）',
        diff,
      };
  }
}

export function isSchemaChangeLog(log: ActivityLog): boolean {
  return getSchemaChanges(log).length > 0;
}

export function schemaOperationLabel(operation: string): string {
  return OPERATION_LABELS[operation] ?? operation;
}

export function schemaOperationColor(operation: string): string {
  switch (operation) {
    case 'CREATE_DATABASE':
    case 'CREATE_TABLE':
      return 'green';
    case 'DROP_DATABASE':
    case 'DROP_TABLE':
      return 'red';
    case 'ALTER_TABLE':
      return 'orange';
    default:
      return 'blue';
  }
}
