import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

function normalizeMarkdown(text: string): string {
  const trimmed = (text || '').trim();
  if (!trimmed) {
    return '';
  }
  const fenced = trimmed.match(/^```(?:markdown|md)?\s*\r?\n([\s\S]*?)\r?\n```$/i);
  if (fenced) {
    return fenced[1].trim();
  }
  return trimmed;
}

interface MarkdownContentProps {
  content: string;
  className?: string;
}

export default function MarkdownContent({ content, className }: MarkdownContentProps) {
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{normalizeMarkdown(content)}</ReactMarkdown>
    </div>
  );
}
