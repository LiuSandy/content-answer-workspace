"""Small provider-neutral gateway fakes shared by architecture tests."""

import json
from unittest.mock import AsyncMock, MagicMock

from app.shared.llm.dto import StructuredLLMResponse


def structured_gateway(content: str):
    gateway = MagicMock()

    async def generate_structured(*, purpose, request):
        try:
            value = request.schema.model_validate(json.loads(content))
            reason = None
        except Exception as error:
            value = None
            reason = str(error)
        return StructuredLLMResponse(
            value=value,
            method_used="function_calling",
            attempts=1,
            degradation_reason=reason,
        )

    gateway.generate_structured = AsyncMock(side_effect=generate_structured)
    return gateway
