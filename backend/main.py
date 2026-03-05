from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db
from api.dependencies import init_services, get_connector, get_scanner
from api import markets_router, arb_router, execution_router, portfolio_router, ws_router
from websocket.ws_manager import ws_manager

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()

_scanner_task: asyncio.Task | None = None


async def _push_opportunities(opps):
    """Callback: push new opportunities to frontend via WebSocket."""
    data = [o.model_dump() for o in opps]
    await ws_manager.broadcast("opportunities", data)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scanner_task

    logger.info("starting_up", dry_run=settings.dry_run)
    await init_db()

    # Initialize services
    init_services()
    connector = get_connector()
    status = await connector.connect_all()
    logger.info("connectors_status", status=status)

    # Start background scanner
    scanner = get_scanner()
    _scanner_task = asyncio.create_task(
        scanner.run_continuous(callback=_push_opportunities)
    )

    yield

    # Shutdown
    if _scanner_task:
        scanner.stop()
        _scanner_task.cancel()
        try:
            await _scanner_task
        except asyncio.CancelledError:
            pass

    await connector.disconnect_all()
    logger.info("shutting_down")


app = FastAPI(
    title="Prediction Market Arbitrage",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(markets_router)
app.include_router(arb_router)
app.include_router(execution_router)
app.include_router(portfolio_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    connector = get_connector()
    return {
        "status": "ok",
        "dry_run": settings.dry_run,
        "platforms": connector.get_status(),
        "ws_clients": ws_manager.client_count,
    }
