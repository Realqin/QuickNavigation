const ANALYSIS_SECTION_MARKERS = [
  '## 🎯 30秒结论',
  '## 🎯',
  '## 30秒结论',
  '## 📊 影响范围速览',
  '## 🔍 主要改动点',
];

/** 匹配正式章节标题（允许 emoji 与文字间有空格）。 */
const SECTION_START_RE = /##\s*[🎯📊🔍]?\s*(?:30\s*秒\s*结论|影响范围速览|主要改动点)/;

/** 去掉模型在正式章节标题前输出的思考/铺垫文字。 */
export function stripAnalysisPreamble(text: string): string {
  const normalized = text.trim();
  if (!normalized) {
    return normalized;
  }

  let bestIdx = -1;
  for (const marker of ANALYSIS_SECTION_MARKERS) {
    const idx = normalized.indexOf(marker);
    if (idx >= 0 && (bestIdx < 0 || idx < bestIdx)) {
      bestIdx = idx;
    }
  }
  if (bestIdx > 0) {
    return normalized.slice(bestIdx).trim();
  }
  if (bestIdx === 0) {
    return normalized;
  }

  const regexMatch = normalized.match(SECTION_START_RE);
  if (regexMatch?.index != null && regexMatch.index > 0) {
    return normalized.slice(regexMatch.index).trim();
  }
  if (regexMatch?.index === 0) {
    return normalized;
  }

  const hashMatch = normalized.match(/^##\s+/m);
  if (hashMatch?.index != null) {
    return normalized.slice(hashMatch.index).trim();
  }
  return normalized;
}
