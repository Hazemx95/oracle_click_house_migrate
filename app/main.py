from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.clickhouse_routes import router as clickhouse_router
from app.api.health_routes import router as health_router
from app.api.oracle_routes import router as oracle_router

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Oracle to ClickHouse Migration Engine")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.include_router(health_router)
app.include_router(oracle_router)
app.include_router(clickhouse_router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")
