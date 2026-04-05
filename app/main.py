import logging

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import TEMPLATES_DIR, SECRET_KEY, ensure_dirs
from app.db import init_db
from app.routes import router, set_templates

logging.basicConfig(level=logging.INFO)

ensure_dirs()
init_db()

app = FastAPI(title="Voz a Texto")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
set_templates(templates)

app.include_router(router)