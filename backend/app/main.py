import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import public, router
from .config import get_settings
from .db import SessionLocal, init_db
from .scheduler import Engine
from .seed import seed


class RedactSecrets(logging.Filter):
    """מסתיר טוקנים בלוגים (למשל טוקן הבוט בכתובת api.telegram.org/bot<TOKEN>)."""
    pat = re.compile(r"(bot)\d+:[A-Za-z0-9_-]+|(apikey=)[A-Za-z0-9]+")

    def filter(self, record):
        record.msg = self.pat.sub(lambda m: (m.group(1) or m.group(2)) + "***", str(record.msg))
        if record.args:
            record.args = tuple(self.pat.sub(lambda m: (m.group(1) or m.group(2)) + "***", str(a)) for a in record.args)
        return True


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for h in logging.getLogger().handlers:
    h.addFilter(RedactSecrets())
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)


def create_app(engine: Engine | None = None, start_scheduler: bool | None = None) -> FastAPI:
    s = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        db = SessionLocal()
        try:
            seed(db, demo=s.demo_mode)
        finally:
            db.close()
        run = s.scheduler_enabled if start_scheduler is None else start_scheduler
        if run:
            app.state.engine.start()
        yield
        await app.state.engine.stop()

    app = FastAPI(title="Ticket Hunter", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.engine = engine or Engine()
    app.include_router(public)
    app.include_router(router)

    @app.middleware("http")
    async def security_headers(request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    static = os.path.abspath(s.static_dir)
    if os.path.isdir(static):
        app.mount("/_next", StaticFiles(directory=os.path.join(static, "_next")), name="next")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                from fastapi import HTTPException
                raise HTTPException(404, "לא נמצא")
            f = os.path.join(static, path)
            if path and os.path.isfile(f) and os.path.abspath(f).startswith(static):
                return FileResponse(f)
            return FileResponse(os.path.join(static, "index.html"))

    return app


app = create_app()
