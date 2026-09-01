"""Acquisition-specific LLM operations over the shared gateway."""

from app.shared.llm.dto import LLMMessage, LLMRequest
from app.shared.llm.port import LLMGatewayPort


class AcquisitionLLM:
    def __init__(self, gateway: LLMGatewayPort) -> None:
        self._gateway = gateway

    async def analyze(self, system_prompt: str, user_prompt: str) -> str:
        result = await self._gateway.generate(
            purpose="acquisition.analysis",
            request=LLMRequest(
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                temperature=0.3,
            ),
        )
        return result.content.strip()

    async def generate_structured(self, request: object) -> str:
        """Return JSON text for legacy acquisition scorers; parsing stays in the use case."""
        messages = [
            LLMMessage.model_validate(message.model_dump())
            for message in request.messages
        ]
        result = await self._gateway.generate(
            purpose="acquisition.analysis",
            request=LLMRequest(
                messages=messages,
                provider=getattr(request, "provider", None),
                model=getattr(request, "model", None),
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ),
        )
        return result.content.strip()


def get_acquisition_llm() -> AcquisitionLLM:
    from app.bootstrap.container import get_llm_gateway

    return AcquisitionLLM(get_llm_gateway())
