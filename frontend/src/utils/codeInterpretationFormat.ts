export function formatDocComment(comment: string, language?: string): string {
  const text = comment.trim();
  if (!text) {
    return '';
  }

  const lang = (language || '').toLowerCase();
  if (lang === 'tsx' || lang === 'jsx') {
    return `{/* # ${text} */}`;
  }
  if (lang === 'python' || lang === 'yaml' || lang === 'yml') {
    return `# ${text}`;
  }
  if (lang === 'sql') {
    return `-- ${text}`;
  }
  return `// # ${text}`;
}
