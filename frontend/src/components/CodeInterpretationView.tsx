import { Typography } from 'antd';
import type { CodeInterpretationBlock, CodeInterpretationPayload } from '../types/codeInterpretation';
import { formatDocComment } from '../utils/codeInterpretationFormat';
import './CodeInterpretationView.css';

interface Props {
  data: CodeInterpretationPayload;
}

function AnnotatedCodeLine({
  block,
  language,
}: {
  block: CodeInterpretationBlock;
  language?: string;
}) {
  const doc = block.comment ? formatDocComment(block.comment, language) : '';

  if (block.type === 'changed' && block.old_code != null) {
    return (
      <div className="code-interpretation__pair">
        {doc ? <div className="code-interpretation__doc">{doc}</div> : null}
        <pre className="code-interpretation__code code-interpretation__code--old">{block.old_code}</pre>
        <pre className="code-interpretation__code code-interpretation__code--new">{block.code}</pre>
      </div>
    );
  }

  const codeClass = [
    'code-interpretation__code',
    block.type === 'added' ? 'code-interpretation__code--new' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="code-interpretation__pair">
      {doc ? <div className="code-interpretation__doc">{doc}</div> : null}
      <pre className={codeClass}>{block.code}</pre>
    </div>
  );
}

export default function CodeInterpretationView({ data }: Props) {
  return (
    <div className="code-interpretation">
      {data.files.map((file) => (
        <section className="code-interpretation__file" key={file.path}>
          <div className="code-interpretation__file-head">
            <Typography.Text className="code-interpretation__file-path">{file.path}</Typography.Text>
            <div className="code-interpretation__legend">
              <span className="code-interpretation__legend-dot code-interpretation__legend-dot--old" />
              <span>修改前</span>
              <span className="code-interpretation__legend-dot code-interpretation__legend-dot--new" />
              <span>修改后</span>
            </div>
          </div>

          <div className="code-interpretation__editor">
            {file.blocks.map((block, index) => {
              if (block.type === 'blank') {
                return <div className="code-interpretation__blank-line" key={index} />;
              }
              return <AnnotatedCodeLine block={block} language={file.language} key={index} />;
            })}
          </div>

          <div className="code-interpretation__summary">
            <div className="code-interpretation__summary-item">
              <span className="code-interpretation__summary-label">修改前逻辑</span>
              <span>{file.summary.before}</span>
            </div>
            <div className="code-interpretation__summary-item">
              <span className="code-interpretation__summary-label">修改后逻辑</span>
              <span>{file.summary.after}</span>
            </div>
            <div className="code-interpretation__summary-item">
              <span className="code-interpretation__summary-label">核心差异</span>
              <span>{file.summary.diff}</span>
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
