import { useCallback, useState } from 'react';
import ApiMonitorActivityChangeModal from '../components/ApiMonitorActivityChangeModal';
import CommitDiffModal from '../components/CommitDiffModal';
import SchemaChangeModal from '../components/SchemaChangeModal';
import type { ActivityLog } from '../types';
import { extractCommitSha, resolveActivityLogDetail } from '../utils/activityLogDetail';

export function useActivityLogDetail() {
  const [schemaChangeLog, setSchemaChangeLog] = useState<ActivityLog | null>(null);
  const [schemaChangeOpen, setSchemaChangeOpen] = useState(false);
  const [apiMonitorChangeLog, setApiMonitorChangeLog] = useState<ActivityLog | null>(null);
  const [apiMonitorChangeOpen, setApiMonitorChangeOpen] = useState(false);
  const [diffLogId, setDiffLogId] = useState<number | null>(null);
  const [diffCommitSha, setDiffCommitSha] = useState<string | null>(null);
  const [diffSummary, setDiffSummary] = useState<string | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);

  const openActivityLogDetail = useCallback((log: ActivityLog) => {
    const detailType = resolveActivityLogDetail(log);
    if (detailType === 'schema') {
      setSchemaChangeLog(log);
      setSchemaChangeOpen(true);
      return;
    }
    if (detailType === 'api-monitor') {
      setApiMonitorChangeLog(log);
      setApiMonitorChangeOpen(true);
      return;
    }
    if (detailType === 'diff') {
      const sha = extractCommitSha(log);
      if (!sha) return;
      setDiffLogId(log.id);
      setDiffCommitSha(sha);
      setDiffSummary(log.summary ?? null);
      setDiffOpen(true);
    }
  }, []);

  const detailModals = (
    <>
      <SchemaChangeModal
        log={schemaChangeLog}
        open={schemaChangeOpen}
        onClose={() => {
          setSchemaChangeOpen(false);
          setSchemaChangeLog(null);
        }}
      />
      <ApiMonitorActivityChangeModal
        log={apiMonitorChangeLog}
        open={apiMonitorChangeOpen}
        onClose={() => {
          setApiMonitorChangeOpen(false);
          setApiMonitorChangeLog(null);
        }}
      />
      <CommitDiffModal
        logId={diffLogId}
        commitSha={diffCommitSha}
        summary={diffSummary}
        open={diffOpen}
        onClose={() => {
          setDiffOpen(false);
          setDiffLogId(null);
          setDiffCommitSha(null);
          setDiffSummary(null);
        }}
      />
    </>
  );

  return { openActivityLogDetail, detailModals };
}
