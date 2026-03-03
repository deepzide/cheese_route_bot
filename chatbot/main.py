import asyncio
import logging
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chatbot.api.chat_router import router as chat_router
from chatbot.api.erp_webhook import router as erp_webhook_router
from chatbot.api.utils.filesystem import create_dirs
from chatbot.api.whatsapp_router import router as whatsapp_router
from chatbot.core.config import config
from chatbot.core.logging_conf import init_logging
from chatbot.core.sentry import init_sentry
from chatbot.db.services import services

init_logging()
logger = logging.getLogger(__name__)

# Database connection retry settings
DB_MAX_RETRIES = 5
DB_RETRY_DELAY = 3  # seconds


async def connect_to_database_with_retry() -> bool:
    """Attempt to connect to database with retries."""
    for attempt in range(1, DB_MAX_RETRIES + 1):
        try:
            logger.info(
                f"🔄 Attempting database connection (attempt {attempt}/{DB_MAX_RETRIES})..."
            )
            await services.database.connect()
            logger.info("✅ Successfully connected to database")
            return True
        except Exception as exc:
            logger.error(
                f"❌ Database connection failed (attempt {attempt}/{DB_MAX_RETRIES}): {exc}"
            )
            if attempt < DB_MAX_RETRIES:
                logger.info(f"⏳ Retrying in {DB_RETRY_DELAY} seconds...")
                await asyncio.sleep(DB_RETRY_DELAY)
            else:
                logger.error(
                    f"💀 All {DB_MAX_RETRIES} database connection attempts failed"
                )
                raise
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting App")
    await connect_to_database_with_retry()
    init_sentry()
    create_dirs()

    yield

    # Shutdown
    try:
        await services.database.disconnect()
        logger.info("✅ Disconnected from database")
    except Exception as exc:
        logger.error(f"❌ Error disconnecting from database: {exc}")


app = FastAPI(
    title="Apacha Bot",
    description="Bot de WhatsApp Apacha: +598 91 656 911",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(whatsapp_router, prefix="/whatsapp")
app.include_router(chat_router)
app.include_router(erp_webhook_router)

# Mount static files for images
""" static_path = Path(__file__).resolve().parents[1] / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
    logger.info(f"✅ static files mounted at /static from {static_path}")
else:
    logger.warning(f"⚠️ static directory not found at {static_path}") """


@app.get("/health")
async def health_check():
    logger.info("Health check requested")
    return {
        "status": "healthy",
        "environment": config.ENV_STATE,
        "ERP_HOST": config.ERP_HOST,
        "USE_FFMPEG": config.USE_FFMPEG,
        "WHATSAPP_BOT_NUMBER": config.WHATSAPP_BOT_NUMBER,
    }


@app.get("/")
async def root():
    logger.info("Root")
    return {
        "message": "Welcome to Apacha Bot",
        "version": "1.0.0",
        "docs": "/docs",
    }
