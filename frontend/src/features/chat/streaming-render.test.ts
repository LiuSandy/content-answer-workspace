import { describe, expect, test } from "bun:test";
import { decorateStreamingMarkdown } from "./markdown-stream-decorator";

describe("streaming markdown decorator", () => {
  test("returns empty string when input is empty", () => {
    expect(decorateStreamingMarkdown("")).toBe("");
  });

  test("does not modify complete plain text", () => {
    const text = "这是一段普通的回答文字，没有任何特殊语法。";
    expect(decorateStreamingMarkdown(text)).toBe(text);
  });

  test("auto-closes incomplete code block during streaming", () => {
    const unclosedCode = "以下是示例代码：\n```typescript\nconst a = 10;\nconsole.log(a);";
    const decorated = decorateStreamingMarkdown(unclosedCode);
    expect(decorated).toBe(unclosedCode + "\n```");
  });

  test("does not add extra closing fence to already closed code block", () => {
    const closedCode = "```typescript\nconst a = 10;\n```\n代码执行完毕。";
    expect(decorateStreamingMarkdown(closedCode)).toBe(closedCode);
  });

  test("handles multiple code blocks where only the last one is unclosed", () => {
    const text = "```bash\npnpm install\n```\n接下来写代码：\n```python\nprint('hello')";
    const decorated = decorateStreamingMarkdown(text);
    expect(decorated).toBe(text + "\n```");
  });

  test("auto-closes incomplete LaTeX block math ($$)", () => {
    const unclosedMath = "根据爱因斯坦质能方程：\n$$ E = mc^2";
    const decorated = decorateStreamingMarkdown(unclosedMath);
    expect(decorated).toBe(unclosedMath + "\n$$");
  });

  test("does not add closing tag when LaTeX block math is already closed", () => {
    const closedMath = "$$ E = mc^2 $$\n推导完毕。";
    expect(decorateStreamingMarkdown(closedMath)).toBe(closedMath);
  });

  test("auto-closes incomplete bold (**)", () => {
    const unclosedBold = "请注意：**这是非常重要的一点";
    const decorated = decorateStreamingMarkdown(unclosedBold);
    expect(decorated).toBe(unclosedBold + "**");
  });

  test("does not falsely trigger math or bold closing inside code block", () => {
    const codeWithMath = "```python\n# $$ cost = $100\nval = 2 ** 3\n";
    const decorated = decorateStreamingMarkdown(codeWithMath);
    // Should close the code block, but not math or bold
    expect(decorated).toBe(codeWithMath + "\n```");
  });

  test("closes a tilde fence with the same marker and length", () => {
    const text = "~~~~typescript\nconst answer = 42;";
    expect(decorateStreamingMarkdown(text)).toBe(text + "\n~~~~");
  });

  test("ignores math and bold markers inside an already closed code block", () => {
    const text = "```text\n$$ price and ** marker\n```\n普通文本";
    expect(decorateStreamingMarkdown(text)).toBe(text);
  });
});
