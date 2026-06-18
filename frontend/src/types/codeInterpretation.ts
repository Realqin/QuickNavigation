export type CodeInterpretationBlockType = 'blank' | 'plain' | 'added' | 'changed';

export interface CodeInterpretationBlock {
  type: CodeInterpretationBlockType;
  code: string;
  old_code?: string;
  comment?: string;
}

export interface CodeInterpretationFile {
  path: string;
  language?: string;
  blocks: CodeInterpretationBlock[];
  summary: {
    before: string;
    after: string;
    diff: string;
  };
}

export interface CodeInterpretationPayload {
  files: CodeInterpretationFile[];
}
