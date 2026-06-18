export type DiffCellType = 'context' | 'delete' | 'add' | 'empty';

export interface SideBySideRow {
  left: string;
  right: string;
  leftType: DiffCellType;
  rightType: DiffCellType;
}

export interface FileDiff {
  oldPath: string;
  newPath: string;
  rows: SideBySideRow[];
  isBinary?: boolean;
}

function displayPath(oldPath: string, newPath: string): string {
  if (oldPath === newPath) return newPath;
  if (!oldPath) return newPath;
  if (!newPath) return oldPath;
  return `${oldPath} → ${newPath}`;
}

function parseHunkLines(hunkLines: string[]): SideBySideRow[] {
  const rows: SideBySideRow[] = [];
  let i = 0;

  while (i < hunkLines.length) {
    const line = hunkLines[i];

    if (line.startsWith('\\')) {
      i += 1;
      continue;
    }

    if (line.startsWith(' ')) {
      const content = line.slice(1);
      rows.push({ left: content, right: content, leftType: 'context', rightType: 'context' });
      i += 1;
      continue;
    }

    if (line.startsWith('-')) {
      const dels: string[] = [];
      while (i < hunkLines.length && hunkLines[i].startsWith('-')) {
        dels.push(hunkLines[i].slice(1));
        i += 1;
      }
      const adds: string[] = [];
      while (i < hunkLines.length && hunkLines[i].startsWith('+')) {
        adds.push(hunkLines[i].slice(1));
        i += 1;
      }
      const max = Math.max(dels.length, adds.length, 1);
      for (let j = 0; j < max; j += 1) {
        const del = dels[j];
        const add = adds[j];
        if (del !== undefined && add !== undefined) {
          rows.push({ left: del, right: add, leftType: 'delete', rightType: 'add' });
        } else if (del !== undefined) {
          rows.push({ left: del, right: '', leftType: 'delete', rightType: 'empty' });
        } else if (add !== undefined) {
          rows.push({ left: '', right: add, leftType: 'empty', rightType: 'add' });
        }
      }
      continue;
    }

    if (line.startsWith('+')) {
      const adds: string[] = [];
      while (i < hunkLines.length && hunkLines[i].startsWith('+')) {
        adds.push(hunkLines[i].slice(1));
        i += 1;
      }
      for (const add of adds) {
        rows.push({ left: '', right: add, leftType: 'empty', rightType: 'add' });
      }
      continue;
    }

    i += 1;
  }

  return rows;
}

function parseFileBlock(block: string): FileDiff | null {
  const lines = block.split('\n');
  if (lines.length === 0) return null;

  let oldPath = '';
  let newPath = '';
  let isBinary = false;
  const hunkLines: string[] = [];
  let inHunk = false;

  for (const line of lines) {
    if (line.startsWith('diff --git ')) {
      const match = line.match(/^diff --git a\/(.+?) b\/(.+)$/);
      if (match) {
        oldPath = match[1];
        newPath = match[2];
      }
      continue;
    }
    if (line.startsWith('--- ')) {
      oldPath = line.slice(4).replace(/^a\//, '');
      if (oldPath === '/dev/null') oldPath = '';
      continue;
    }
    if (line.startsWith('+++ ')) {
      newPath = line.slice(4).replace(/^b\//, '');
      if (newPath === '/dev/null') newPath = '';
      continue;
    }
    if (line.includes('Binary files') || line.startsWith('GIT binary patch')) {
      isBinary = true;
      continue;
    }
    if (line.startsWith('@@')) {
      inHunk = true;
      continue;
    }
    if (inHunk) {
      hunkLines.push(line);
    }
  }

  if (!oldPath && !newPath) {
    oldPath = 'unknown';
    newPath = 'unknown';
  }

  const rows = isBinary ? [] : parseHunkLines(hunkLines);

  if (rows.length === 0 && !isBinary) return null;

  return {
    oldPath: oldPath || newPath,
    newPath: newPath || oldPath,
    rows,
    isBinary,
  };
}

export function parseUnifiedDiff(diff: string): FileDiff[] {
  const trimmed = diff.trim();
  if (!trimmed) return [];

  const blocks = trimmed.split(/^diff --git /m).filter(Boolean);
  const files: FileDiff[] = [];

  if (blocks.length === 0 || (blocks.length === 1 && !trimmed.startsWith('diff --git'))) {
    const single = parseFileBlock(trimmed);
    if (single) files.push(single);
    return files;
  }

  for (const block of blocks) {
    const parsed = parseFileBlock(`diff --git ${block}`);
    if (parsed) files.push(parsed);
  }

  return files;
}

export function fileDiffTitle(file: FileDiff): string {
  return displayPath(file.oldPath, file.newPath);
}
