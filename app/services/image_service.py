from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.config.runtime import GENERATED_IMAGES_DIR, get_required_env
from app.api.schemas.workflow import QuestionItem


class GeneratedImagePayload(dict):
    """表示一次图片生成的结构化结果；这样回答生成流程可以同时拿到图片路径和所用提示词。"""


class ImageGenerationService:
    """封装图片生成与本地落盘；这样回答工作流只关心生成结果，不关心图片服务细节和文件格式处理。"""

    def __init__(self) -> None:
        """初始化延迟客户端；这样只有真正请求图片时才读取图片模型配置。"""

        self._client: OpenAI | None = None

    def get_client(self) -> OpenAI:
        """获取图片生成客户端；这样图片能力可以复用 OpenAI SDK，并独立于文本模型配置。"""

        if self._client is None:
            api_key = get_required_env("IMAGE_API_KEY")
            base_url = get_required_env("IMAGE_BASE_URL").strip().rstrip("/")
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        return self._client

    async def generate_images_for_answer(self, item: QuestionItem, answer_markdown: str) -> GeneratedImagePayload:
        """根据回答内容生成真实图片；这样前端不必自己画图，问题对象可以直接挂载可展示图片。"""

        prompts = self._extract_image_prompts(answer_markdown, item)
        if not prompts:
            return GeneratedImagePayload(images=[], imagePrompts=[])

        generated_urls: list[str] = []
        used_prompts: list[str] = []
        for index, prompt in enumerate(prompts, start=1):
            image_url = self._generate_single_image(prompt, item, index)
            generated_urls.append(image_url)
            used_prompts.append(prompt)
        return GeneratedImagePayload(images=generated_urls, imagePrompts=used_prompts)

    def _extract_image_prompts(self, answer_markdown: str, item: QuestionItem) -> list[str]:
        """从回答里的配图建议提炼出图片提示词；这样图片生成可以直接复用已产出的内容语义，而不是重新瞎猜。"""

        section_match = re.search(
            r"##\s*配图建议\s*(.*?)(?:\n##\s*|$)",
            answer_markdown,
            re.S,
        )
        section = section_match.group(1).strip() if section_match else ""
        raw_lines = [
            line.strip(" -\t")
            for line in section.splitlines()
            if line.strip() and not line.strip().startswith("![](")
        ]
        if not raw_lines:
            raw_lines = [f"{item.topic} 主题插图，围绕问题《{item.title}》生成一张清晰的信息图"]

        prompts: list[str] = []
        for line in raw_lines[:2]:
            prompt = "\n".join(
                [
                    "请生成一张真实、清晰、适合中文技术问答配图的信息图。",
                    "不要生成纯文字海报，不要只生成大段中文句子，不要留白海报感。",
                    "画面要包含明确结构、图示、模块关系或流程关系，适合直接插入问答回答。",
                    f"问题标题：{item.title}",
                    f"问题主题：{item.topic}",
                    f"配图要求：{line}",
                ]
            )
            prompts.append(prompt)
        return prompts

    def _generate_single_image(self, prompt: str, item: QuestionItem, index: int) -> str:
        """调用图片模型并保存单张图片；这样每条配图建议都能落成本地文件并生成稳定访问路径。"""

        client = self.get_client()
        model = get_required_env("IMAGE_MODEL")
        result = client.images.generate(
            model=model,
            prompt=prompt,
            size="1536x1024",
        )
        data = result.data[0] if result.data else None
        if not data:
            raise ValueError("Image model returned empty image result")

        image_bytes = self._extract_image_bytes(data)
        extension = self._detect_extension(image_bytes)
        file_path = self._build_image_path(item, index, extension)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(image_bytes)
        return f"/generated-images/{file_path.name}"

    def _extract_image_bytes(self, data: Any) -> bytes:
        """从图片模型响应中提取二进制内容；这样无论返回 base64 还是图片 URL 都能统一落盘。"""

        b64_json = getattr(data, "b64_json", None) or (data.get("b64_json") if isinstance(data, dict) else None)
        if b64_json:
            try:
                return base64.b64decode(b64_json)
            except (binascii.Error, ValueError) as error:
                raise ValueError("Failed to decode generated image payload") from error
        raise ValueError("Image model did not return base64 image content")

    def _detect_extension(self, image_bytes: bytes) -> str:
        """识别图片扩展名；这样本地文件保存时能使用正确后缀并方便浏览器展示。"""

        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return "jpg"
        if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
            return "webp"
        return "png"

    def _build_image_path(self, item: QuestionItem, index: int, extension: str) -> Path:
        """为生成图片创建稳定文件名；这样同一问题的配图文件可追踪且不容易冲突。"""

        GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_question_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", item.id).strip("-") or "question"
        return GENERATED_IMAGES_DIR / f"{safe_question_id}-{timestamp}-{index}.{extension}"
