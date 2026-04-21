import logging

import sentry_sdk
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from chatbot.core.config import config

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
        enable_logs=True,
        integrations=[
            HttpxIntegration(),  # Traza llamadas HTTP salientes (ERP, OpenAI, etc.)
            SqlalchemyIntegration(),  # Traza queries a la base de datos
        ],
    )
    logger.info("Sentry initialized")
