import sys
from loguru import logger
from config.settings import settings

# Configure logger
logger.remove()

# Console output
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
           "<level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
           "<level>{message}</level>",
    level=settings.LOG_LEVEL,
    colorize=True,
)

# File output
logger.add(
    settings.LOG_FILE,
    format="{time:YYYY-MM-DD HH:mm:ss} | "
           "{level: <8} | "
           "{name}:{function}:{line} - {message}",
    level=settings.LOG_LEVEL,
    rotation="10 MB",
    retention="30 days",
    compression="zip",
)

# Export logger
__all__ = ["logger"]