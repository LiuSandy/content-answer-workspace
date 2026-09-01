"""Publishing-specific LLM operations over the shared gateway."""

from app.shared.llm.dto import LLMMessage, LLMRequest
from app.shared.llm.port import LLMGatewayPort


class PublishingLLM:
    def __init__(self, gateway: LLMGatewayPort) -> None:
        self._gateway = gateway

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        response = await self._gateway.generate(
            purpose="publishing.analysis",
            request=LLMRequest(
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
        )
        return response.content.strip()


def get_publishing_llm() -> PublishingLLM:
    from app.bootstrap.container import get_llm_gateway

    return PublishingLLM(get_llm_gateway())
