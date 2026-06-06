from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes.config import router as config_router
from .api.routes.session import router as session_router
from .api.routes.workflow import router as workflow_router
from .core.config import load_env_file
from .models import RegeneratePayload, RunPayload, SessionPayload
from .services.answer_service import generate_answer
from .services.session_service import cookie_status, read_latest_session, save_session
from .services.zhihu_service import collect_questions

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"

app = FastAPI()


@app.exception_handler(Exception)
async def handle_exception(_: Request, error: Exception) -> JSONResponse:
    if isinstance(error, HTTPException):
        return JSONResponse(
            status_code=error.status_code,
            content={"ok": False, "error": {"message": str(error.detail)}},
        )
    return JSONResponse(status_code=500, content={"ok": False, "error": {"message": str(error)}})


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True, "data": {"status": "ok"}})


app.include_router(config_router)
app.include_router(session_router)
app.include_router(workflow_router)


# Legacy compatibility endpoints while the frontend is being migrated.
@app.get("/api/config")
async def legacy_get_config() -> JSONResponse:
    response = await config_router.routes[0].endpoint()
    return response


@app.get("/api/session/latest")
async def legacy_get_latest_session() -> JSONResponse:
    return JSONResponse({"session": read_latest_session()})


@app.get("/api/cookie-status")
async def legacy_cookie_status() -> JSONResponse:
    return JSONResponse(cookie_status(os.getenv("ZHIHU_COOKIE_FILE", "").strip()))


@app.post("/api/run")
async def legacy_run(payload: RunPayload) -> JSONResponse:
    try:
        result = await collect_questions(payload.model_dump(by_alias=True))
        return JSONResponse(result.model_dump(by_alias=True))
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/regenerate")
async def legacy_regenerate(payload: RegeneratePayload) -> JSONResponse:
    try:
        from .core.config import get_workflow_config

        config = get_workflow_config()
        answer = await generate_answer(
            payload.item,
            payload.answer_style or config.answer_style,
            config.cta_text,
            payload.system_prompt or config.system_prompt,
        )
        return JSONResponse({"answer": answer})
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/generate-all")
async def legacy_generate_all(payload: SessionPayload) -> JSONResponse:
    try:
        from .core.config import get_workflow_config

        config = get_workflow_config(
            {
                "answerStyle": payload.answer_style,
                "systemPrompt": payload.system_prompt,
            }
        )
        items = []
        for item in payload.items:
            answer = await generate_answer(
                item,
                payload.answer_style or config.answer_style,
                config.cta_text,
                payload.system_prompt or config.system_prompt,
            )
            items.append(item.model_copy(update={"answer": answer}))
        return JSONResponse({"items": [item.model_dump(by_alias=True) for item in items]})
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/save")
async def legacy_save(payload: SessionPayload) -> JSONResponse:
    file_path = save_session(payload)
    return JSONResponse({"ok": True, "filePath": file_path})


if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
else:
    @app.get("/")
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "data": {
                    "message": "Frontend dist is not built yet. Run the frontend dev server or build frontend/dist first."
                },
            }
        )


def main() -> None:
    load_env_file()
    port = int(os.getenv("PORT", "3000"))
    auto_open = os.getenv("AUTO_OPEN_BROWSER", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173").strip()
    fallback_url = f"http://127.0.0.1:{port}"
    url = frontend_url if os.getenv("USE_VITE_DEV_SERVER", "true").strip().lower() in {"1", "true", "yes", "on"} else fallback_url

    if auto_open:
        threading.Timer(1, lambda: webbrowser.open(url)).start()

    uvicorn.run("app.server:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    main()
