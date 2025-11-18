"""Entry point for DOGE funding rate bot."""

import logging
import sys
from config import Config
from bot import FundingBot


def setup_logging():
    """Configure logging."""
    log_level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('bot.log')
        ]
    )


def main():
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("="*60)
    logger.info("DOGE Funding Rate Bot - OKX")
    logger.info("="*60)
    logger.info(f"Symbol: {Config.SYMBOL}")
    logger.info(f"Check Interval: {Config.CHECK_INTERVAL}s")
    logger.info(f"Funding Threshold: {Config.FUNDING_THRESHOLD * 100}%")

    if Config.has_api_credentials():
        logger.info("API credentials: Configured ✓")
    else:
        logger.warning("API credentials: Not configured (using public endpoints only)")

    logger.info("="*60)

    # Create and run bot
    bot = FundingBot()

    try:
        bot.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
