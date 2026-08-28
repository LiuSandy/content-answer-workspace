/**
 * 流式 Markdown 语法临时闭合修饰器：
 * 在流式生成阶段，大模型吐出的代码块（```）、数学公式（$$）或粗体（**）往往处于半闭合状态，
 * 这会导致 Markdown 解析器将其误判为普通文本或引起剧烈的视觉跳变（Layout Shift）。
 *
 * 该工具函数在交给 Markdown 渲染引擎前，临时为未闭合的语法补齐闭合标记，
 * 仅用于视觉展示，不修改底层原始状态数据。
 */

export function decorateStreamingMarkdown(raw: string): string {
  if (!raw) return "";

  let decorated = raw;

  // 1. 检查代码块围栏（``` 或 ~~~）
  const lines = decorated.split("\n");
  let inCodeFence = false;
  for (const line of lines) {
    if (/^\s*(?:`{3,}|~{3,})/.test(line)) {
      inCodeFence = !inCodeFence;
    }
  }

  if (inCodeFence) {
    // 补齐末尾闭合代码围栏
    decorated += "\n```";
    return decorated;
  }

  // 2. 检查块级 LaTeX 数学公式（$$ ... $$）
  // 仅在不在代码块内部时检测
  const blockMathMatches = decorated.match(/(?<!\\)\$\$/g);
  if (blockMathMatches && blockMathMatches.length % 2 === 1) {
    decorated += "\n$$";
    return decorated;
  }

  // 3. 检查未闭合的加粗标记（**）
  const boldMatches = decorated.match(/(?<!\\)\*\*/g);
  if (boldMatches && boldMatches.length % 2 === 1) {
    decorated += "**";
  }

  return decorated;
}
