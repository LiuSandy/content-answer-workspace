from __future__ import annotations

import asyncio
import json
import sys

from .workflow import load_env_file, run_workflow, save_workflow_result


def main() -> None:
    async def _run() -> None:
        load_env_file()
        result = await run_workflow()
        files = save_workflow_result(result)
        print(json.dumps({**files, "total": len(result.items)}, ensure_ascii=False, indent=2))

    try:
        asyncio.run(_run())
    except Exception as error:  # noqa: BLE001
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
