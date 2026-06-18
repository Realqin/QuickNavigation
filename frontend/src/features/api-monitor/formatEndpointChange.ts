import type { ApiMonitorParameter } from '../../types/apiMonitor';

export interface EndpointSnapshot {
  method?: string;
  path?: string;
  summary?: string;
  tags?: string[];
  request_content_type?: string;
  response_content_type?: string;
  parameters?: ApiMonitorParameter[];
  responses?: Array<{
    status_code?: string;
    description?: string;
    data_type?: string;
    schema_name?: string | null;
    properties?: ApiMonitorParameter[];
  }>;
}

export interface EndpointDiffJson {
  summary_changed?: { before?: string; after?: string };
  request_content_type_changed?: boolean;
  response_content_type_changed?: boolean;
  responses_changed?: boolean;
  parameters?: {
    added?: ApiMonitorParameter[];
    removed?: ApiMonitorParameter[];
    modified?: Array<{
      name?: string;
      in?: string;
      before?: ApiMonitorParameter;
      after?: ApiMonitorParameter;
    }>;
  };
}

export type CompareSideHighlight = 'none' | 'removed' | 'added';

export interface HighlightedText {
  text: string;
  highlight: CompareSideHighlight;
}

export interface SnapshotCompareSide {
  title: HighlightedText;
  summary: HighlightedText;
  requestContentType: HighlightedText;
  responseContentType: HighlightedText;
  parameters: HighlightedText[];
  responses: HighlightedText[];
}

export interface EndpointCompareColumns {
  before: SnapshotCompareSide | null;
  after: SnapshotCompareSide | null;
  beforeEmptyText: string;
  afterEmptyText: string;
}

interface EndpointChangeLike {
  change_type: string;
  before_json?: EndpointSnapshot | Record<string, unknown> | null;
  after_json?: EndpointSnapshot | Record<string, unknown> | null;
  diff_json?: EndpointDiffJson | Record<string, unknown> | null;
}

function paramKey(param: Pick<ApiMonitorParameter, 'in' | 'name'>): string {
  return `${param.in}:${param.name}`;
}

function formatParamLine(param: ApiMonitorParameter): string {
  const desc = param.description?.trim();
  return desc ? `${paramLabel(param)}：${desc}` : paramLabel(param);
}

function highlight(text: string, sideHighlight: CompareSideHighlight): HighlightedText {
  return { text, highlight: sideHighlight };
}

function sideHighlightForChange(
  changed: boolean,
  changeType: string,
  side: 'before' | 'after',
): CompareSideHighlight {
  if (changeType === 'added') {
    return side === 'after' ? 'added' : 'none';
  }
  if (changeType === 'removed') {
    return side === 'before' ? 'removed' : 'none';
  }
  if (!changed) {
    return 'none';
  }
  return side === 'before' ? 'removed' : 'added';
}

function diffStringLines(beforeLines: string[], afterLines: string[]): {
  before: HighlightedText[];
  after: HighlightedText[];
} {
  const beforeSet = new Set(beforeLines);
  const afterSet = new Set(afterLines);
  return {
    before: beforeLines.map((line) =>
      highlight(line, afterSet.has(line) ? 'none' : 'removed'),
    ),
    after: afterLines.map((line) =>
      highlight(line, beforeSet.has(line) ? 'none' : 'added'),
    ),
  };
}

function buildParameterHighlights(
  beforeParams: ApiMonitorParameter[] | undefined,
  afterParams: ApiMonitorParameter[] | undefined,
  changeType: string,
  paramDiff?: EndpointDiffJson['parameters'],
): { before: HighlightedText[]; after: HighlightedText[] } {
  const before = beforeParams || [];
  const after = afterParams || [];

  if (changeType === 'added') {
    return {
      before: [highlight('（无参数）', 'none')],
      after: (after.length ? after.map((param) => highlight(formatParamLine(param), 'added')) : [
        highlight('（无参数）', 'added'),
      ]),
    };
  }
  if (changeType === 'removed') {
    return {
      before: (before.length ? before.map((param) => highlight(formatParamLine(param), 'removed')) : [
        highlight('（无参数）', 'removed'),
      ]),
      after: [highlight('（无参数）', 'none')],
    };
  }

  if (!paramDiff) {
    return diffStringLines(formatParameterLines(before), formatParameterLines(after));
  }

  const removedKeys = new Set((paramDiff.removed || []).map((item) => paramKey(item)));
  const addedKeys = new Set((paramDiff.added || []).map((item) => paramKey(item)));
  const modifiedMap = new Map(
    (paramDiff.modified || []).map((item) => [
      paramKey(item.before || item.after || { in: item.in || '', name: item.name || '' }),
      item,
    ]),
  );

  const beforeLines = before.map((param) => {
    const key = paramKey(param);
    if (removedKeys.has(key) || modifiedMap.has(key)) {
      const mod = modifiedMap.get(key);
      const source = mod?.before || param;
      return highlight(formatParamLine(source), 'removed');
    }
    return highlight(formatParamLine(param), 'none');
  });

  const afterLines = after.map((param) => {
    const key = paramKey(param);
    if (addedKeys.has(key) || modifiedMap.has(key)) {
      const mod = modifiedMap.get(key);
      const source = mod?.after || param;
      return highlight(formatParamLine(source), 'added');
    }
    return highlight(formatParamLine(param), 'none');
  });

  return {
    before: beforeLines.length ? beforeLines : [highlight('（无参数）', 'none')],
    after: afterLines.length ? afterLines : [highlight('（无参数）', 'none')],
  };
}

function paramLabel(param: ApiMonitorParameter): string {
  const required = param.required ? '必填' : '可选';
  const typeText = param.schema_name || param.data_type || 'unknown';
  return `${param.in} / ${param.name} (${typeText}, ${required})`;
}

function snapshotTitle(snapshot: EndpointSnapshot): string {
  return `${snapshot.method || ''} ${snapshot.path || ''}`.trim() || '未知接口';
}

function buildCompareSide(
  snapshot: EndpointSnapshot,
  side: 'before' | 'after',
  changeType: string,
  peer: EndpointSnapshot | null | undefined,
  diff: EndpointDiffJson | null | undefined,
  paramHighlights: { before: HighlightedText[]; after: HighlightedText[] },
  responseHighlights: { before: HighlightedText[]; after: HighlightedText[] },
): SnapshotCompareSide {
  const titleChanged = peer ? snapshotTitle(snapshot) !== snapshotTitle(peer) : changeType !== 'added';
  const summaryChanged =
    Boolean(diff?.summary_changed) ||
    (peer ? (snapshot.summary || '') !== (peer.summary || '') : changeType !== 'added');
  const requestTypeChanged =
    Boolean(diff?.request_content_type_changed) ||
    (peer
      ? (snapshot.request_content_type || '') !== (peer.request_content_type || '')
      : changeType !== 'added');
  const responseTypeChanged =
    Boolean(diff?.response_content_type_changed) ||
    (peer
      ? (snapshot.response_content_type || '') !== (peer.response_content_type || '')
      : changeType !== 'added');

  const paramLines = side === 'before' ? paramHighlights.before : paramHighlights.after;
  const responseLines = side === 'before' ? responseHighlights.before : responseHighlights.after;

  return {
    title: highlight(
      snapshotTitle(snapshot),
      sideHighlightForChange(titleChanged, changeType, side),
    ),
    summary: highlight(
      snapshot.summary || '（无摘要）',
      sideHighlightForChange(summaryChanged, changeType, side),
    ),
    requestContentType: highlight(
      snapshot.request_content_type || '（未定义）',
      sideHighlightForChange(requestTypeChanged, changeType, side),
    ),
    responseContentType: highlight(
      snapshot.response_content_type || '（未定义）',
      sideHighlightForChange(responseTypeChanged, changeType, side),
    ),
    parameters: paramLines,
    responses: responseLines,
  };
}

export function buildEndpointCompareColumns(change: EndpointChangeLike): EndpointCompareColumns {
  const changeType = change.change_type;
  const diff = (change.diff_json || null) as EndpointDiffJson | null;
  const beforeSnapshot = (change.before_json || null) as EndpointSnapshot | null;
  const afterSnapshot = (change.after_json || null) as EndpointSnapshot | null;

  const showBefore = changeType !== 'added';
  const showAfter = changeType !== 'removed';

  const paramHighlights = buildParameterHighlights(
    beforeSnapshot?.parameters,
    afterSnapshot?.parameters,
    changeType,
    diff?.parameters,
  );

  const responseHighlights =
    changeType === 'added'
      ? {
          before: [highlight('（无响应定义）', 'none')],
          after: (afterSnapshot?.responses?.length
            ? formatResponseLines(afterSnapshot.responses).map((line) => highlight(line, 'added'))
            : [highlight('（无响应定义）', 'added')]),
        }
      : changeType === 'removed'
        ? {
            before: (beforeSnapshot?.responses?.length
              ? formatResponseLines(beforeSnapshot.responses).map((line) => highlight(line, 'removed'))
              : [highlight('（无响应定义）', 'removed')]),
            after: [highlight('（无响应定义）', 'none')],
          }
        : diffStringLines(
            formatResponseLines(beforeSnapshot?.responses),
            formatResponseLines(afterSnapshot?.responses),
          );

  return {
    before:
      showBefore && beforeSnapshot
        ? buildCompareSide(
            beforeSnapshot,
            'before',
            changeType,
            afterSnapshot,
            diff,
            paramHighlights,
            responseHighlights,
          )
        : null,
    after:
      showAfter && afterSnapshot
        ? buildCompareSide(
            afterSnapshot,
            'after',
            changeType,
            beforeSnapshot,
            diff,
            paramHighlights,
            responseHighlights,
          )
        : null,
    beforeEmptyText: showBefore ? '（改动前无记录）' : '（本次为新增接口）',
    afterEmptyText: showAfter ? '（改动后无记录）' : '（本次为删除接口）',
  };
}

export interface DiffSummaryItem {
  text: string;
  tone: 'added' | 'removed' | 'modified';
}

export function buildDiffSummaryItems(diff?: EndpointDiffJson | null): DiffSummaryItem[] {
  if (!diff) {
    return [];
  }
  const items: DiffSummaryItem[] = [];
  if (diff.summary_changed) {
    items.push({
      text: `摘要：${diff.summary_changed.before || '（空）'} → ${diff.summary_changed.after || '（空）'}`,
      tone: 'modified',
    });
  }
  if (diff.request_content_type_changed) {
    items.push({ text: '请求 Content-Type 发生变更', tone: 'modified' });
  }
  if (diff.response_content_type_changed) {
    items.push({ text: '响应 Content-Type 发生变更', tone: 'modified' });
  }
  if (diff.responses_changed) {
    items.push({ text: '响应定义发生变更', tone: 'modified' });
  }
  for (const param of diff.parameters?.added || []) {
    items.push({ text: `新增参数：${paramLabel(param)}`, tone: 'added' });
  }
  for (const param of diff.parameters?.removed || []) {
    items.push({ text: `删除参数：${paramLabel(param)}`, tone: 'removed' });
  }
  for (const param of diff.parameters?.modified || []) {
    items.push({ text: `修改参数：${param.in}/${param.name}`, tone: 'modified' });
  }
  return items;
}

export function formatParameterLines(parameters: ApiMonitorParameter[] | undefined): string[] {
  if (!parameters?.length) {
    return ['（无参数）'];
  }
  return parameters.map((param) => {
    const desc = param.description?.trim();
    return desc ? `${paramLabel(param)}：${desc}` : paramLabel(param);
  });
}

export function formatResponseLines(
  responses: EndpointSnapshot['responses'],
): string[] {
  if (!responses?.length) {
    return ['（无响应定义）'];
  }
  return responses.map((item) => {
    const code = item.status_code || '?';
    const desc = item.description?.trim();
    const typeText = item.schema_name || item.data_type || '';
    const base = typeText ? `${code} (${typeText})` : code;
    return desc ? `${base}：${desc}` : base;
  });
}

export function buildDiffSummaryLines(diff?: EndpointDiffJson | null): string[] {
  if (!diff) {
    return [];
  }
  const lines: string[] = [];
  if (diff.summary_changed) {
    lines.push(`摘要：${diff.summary_changed.before || '（空）'} → ${diff.summary_changed.after || '（空）'}`);
  }
  if (diff.request_content_type_changed) {
    lines.push('请求 Content-Type 发生变更');
  }
  if (diff.response_content_type_changed) {
    lines.push('响应 Content-Type 发生变更');
  }
  if (diff.responses_changed) {
    lines.push('响应定义发生变更');
  }
  for (const param of diff.parameters?.added || []) {
    lines.push(`新增参数：${paramLabel(param)}`);
  }
  for (const param of diff.parameters?.removed || []) {
    lines.push(`删除参数：${paramLabel(param)}`);
  }
  for (const param of diff.parameters?.modified || []) {
    lines.push(`修改参数：${param.in}/${param.name}`);
  }
  return lines;
}

export function snapshotToDisplayBlocks(snapshot: EndpointSnapshot | null | undefined) {
  if (!snapshot) {
    return null;
  }
  return {
    title: `${snapshot.method || ''} ${snapshot.path || ''}`.trim() || '未知接口',
    summary: snapshot.summary || '（无摘要）',
    requestContentType: snapshot.request_content_type || '（未定义）',
    responseContentType: snapshot.response_content_type || '（未定义）',
    parameters: formatParameterLines(snapshot.parameters),
    responses: formatResponseLines(snapshot.responses),
  };
}
