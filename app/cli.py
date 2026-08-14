from __future__ import annotations

import asyncio
import json
import sys

from .services.workflow_compat import load_env_file, run_workflow, save_workflow_result


def main() -> None:
    """运行命令行工作流入口；这样本地脚本可以复用后端采集、生成和保存能力。"""

    async def _run() -> None:
        """执行异步 CLI 主流程；这样 main 可以用 asyncio.run 包装后端异步工作流。"""

        load_env_file()
        result = await run_workflow()
        files = save_workflow_result(result)
        print(json.dumps({**files, "total": len(result.items)}, ensure_ascii=False, indent=2))

    try:
        asyncio.run(_run())
    except Exception as error:  # noqa: BLE001
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
