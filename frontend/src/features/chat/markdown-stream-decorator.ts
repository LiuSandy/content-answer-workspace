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

  // 1. 检查代码块围栏（``` 或 ~~~），并记录围栏字符与最小长度。
  const lines = decorated.split("\n");
  let openFence: { marker: "`" | "~"; length: number } | null = null;
  const outsideFenceLines: string[] = [];
  for (const line of lines) {
    const fenceMatch = line.match(/^\s*(`{3,}|~{3,})(.*)$/);
    if (!openFence) {
      if (fenceMatch) {
        openFence = {
          marker: fenceMatch[1][0] as "`" | "~",
          length: fenceMatch[1].length,
        };
      } else {
        outsideFenceLines.push(line);
      }
      continue;
    }

    if (
      fenceMatch &&
      fenceMatch[1][0] === openFence.marker &&
      fenceMatch[1].length >= openFence.length &&
      !fenceMatch[2].trim()
    ) {
      openFence = null;
    }
  }

  if (openFence) {
    decorated += `\n${openFence.marker.repeat(openFence.length)}`;
    return decorated;
  }

  // 已闭合代码块里的符号不参与数学公式和粗体计数。
  const syntaxText = outsideFenceLines.join("\n");

  // 2. 检查块级 LaTeX 数学公式（$$ ... $$）
  // 仅在不在代码块内部时检测
  const blockMathMatches = syntaxText.match(/(?<!\\)\$\$/g);
  if (blockMathMatches && blockMathMatches.length % 2 === 1) {
    decorated += "\n$$";
    return decorated;
  }

  // 3. 检查未闭合的加粗标记（**）
  const boldMatches = syntaxText.match(/(?<!\\)\*\*/g);
  if (boldMatches && boldMatches.length % 2 === 1) {
    decorated += "**";
  }

  return decorated;
}
