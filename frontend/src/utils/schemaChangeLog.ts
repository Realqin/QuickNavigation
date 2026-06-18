import type { ActivityLog } from '../types';

export interface SchemaChangeItem {
  operation: string;
  table?: string | null;
  summary: string;
  details?: string[];
}

const OPERATION_LABELS: Record<string, string> = {
  CREATE_DATABASE: '新增库',
  DROP_DATABASE: '删除库',
  CREATE_TABLE: '新增表',
  DROP_TABLE: '删除表',
  ALTER_TABLE: '修改表',
};

export function getSchemaChanges(log: ActivityLog): SchemaChangeItem[] {
  if (log.payload?.event !== 'schema_change') {
    return [];
  }
  if (Array.isArray(log.payload.changes) && log.payload.changes.length > 0) {
    return (log.payload.changes as SchemaChangeItem[]).map((item) => ({
      operation: String(item.operation ?? ''),
      table: item.table ?? null,
      summary: String(item.summary ?? ''),
      details: Array.isArray(item.details) ? item.details.map(String) : [],
    }));
  }
  if (log.payload.operation) {
    const preview = log.payload.sql_preview;
    return [
      {
        operation: String(log.payload.operation),
        table: (log.payload.table as string | null | undefined) ?? null,
        summary: String(log.summary ?? log.payload.operation),
        details:
          typeof preview === 'string' && preview
            ? preview.split('; ').map((item) => item.trim()).filter(Boolean)
            : [],
      },
    ];
  }
  return [];
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
