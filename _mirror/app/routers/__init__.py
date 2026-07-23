from .api import router as api_router
from .web import router as web_router

routers = [
    api_router,
    web_router,
]
