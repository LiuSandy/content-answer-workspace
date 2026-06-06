from __future__ import annotations

from openai import OpenAI

from ..core.config import get_required_env
from ..models import QuestionItem

_openai_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    _openai_client = OpenAI(
        api_key=get_required_env("OPENAI_API_KEY"),
        base_url=get_required_env("OPENAI_BASE_URL").strip().rstrip("/"),
    )
    return _openai_client


async def generate_answer(item: QuestionItem, answer_style: str, cta_text: str, system_prompt: str) -> str:
    client = get_openai_client()
    model = get_required_env("OPENAI_MODEL")
    prompt = "\n".join(
        [
            "你是一名有长期写作经验的中文作者，擅长把观点、事实、经历和观察自然地讲出来。",
            f"请围绕下面这个知乎问题写一篇适合发布到知乎的原创回答，整体风格要求：{answer_style}",
            "要求：",
            "1. 回答要像真人写的，不要有AI腔，不要像标准化模板，不要一上来就分点罗列。",
            "2. 尽量从真实世界的经验、常见现象、行业观察、亲历感受、见过的案例中展开，让内容有生活感和人味。",
            "3. 可以像一个有见识的人在认真展开自己的看法，允许有自然转折、个人判断和细节，不要写成论文，也不要写成客服话术。",
            "4. 如果适合这个问题，可以先讲一个小观察、一个真实场景、一个常见误区，再进入观点。",
            "5. 如果提到案例、故事、经历感表达，必须具体到什么场景、出了什么问题、为什么会这样、后来怎么调整、为什么调整后有效。不要出现空泛的伪故事。",
            "6. 明确禁止这类空话：有一次我遇到一个问题后来解决了、一个朋友告诉我答案、一个项目上线前出了问题后来优化了。如果不能讲具体细节，就不要硬写故事。",
            "7. 不要虚构具体履历、不要编造自己亲身做过某件事；如果不能确认真实细节，就改写成对普遍现象的分析。",
            "8. 每个判断都尽量给出依据，可以是常识、现象、机制、例子、对比、后果之一。",
            "9. 每一段都必须有信息增量，不能只是把空泛结论换一种说法重复一遍。",
            "10. 禁止使用大而空的表达来冒充分析，例如：性能瓶颈、用户体验大打折扣、引入合适的数据结构、效率大幅提升。除非后面马上解释清楚。",
            "11. 如果写技术例子，至少交代三件事里的两件：原来怎么做、问题为什么出现、后来改成什么、为什么改完有效。",
            "12. 少下笼统结论，多写可感知的细节。",
            "13. 不要写得太格式化，除非内容确实需要，否则尽量少用第一第二第三。",
            "14. 使用中文 Markdown，但正文优先像自然文章，适度分段即可。",
            "15. 在输出前自行检查一遍：如果某句话可以套在几乎任何问题上，那这句话就不够具体，应该重写。",
            "16. 结尾必须单独一段加入指定引流文案。",
            "",
            f"问题标题：{item.title}",
            f"问题链接：{item.url}",
            f"问题分类：{item.topic or '未分类'}",
            f"问题摘要：{item.excerpt or '无'}",
            f"结尾引流文案：{cta_text}",
        ]
    )
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "developer",
                "content": system_prompt,
            },
            {"role": "user", "content": prompt},
        ],
    )
    content = completion.choices[0].message.content if completion.choices else None
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content).strip()
    raise ValueError("OpenAI returned empty answer content")
