"""Test script for bot functionality."""

import logging
import sys
from config import Config
from bot import FundingBot

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

def test_bot():
    """Test bot functionality."""
    logger.info("="*60)
    logger.info("Testing DOGE Funding Rate Bot")
    logger.info("="*60)

    try:
        # Create bot instance
        bot = FundingBot()
        logger.info("✓ Bot instance created successfully")

        # Display funding history
        logger.info("\nTesting funding history retrieval...")
        bot.display_funding_history(limit=3)
        logger.info("✓ Funding history retrieved successfully")

        # Run single check
        logger.info("\nTesting single check cycle...")
        bot.run_once()
        logger.info("✓ Single check completed successfully")

        logger.info("\n" + "="*60)
        logger.info("All tests passed! Bot is fully functional.")
        logger.info("="*60)
        return 0

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1

if __name__ == '__main__':
    sys.exit(test_bot())
