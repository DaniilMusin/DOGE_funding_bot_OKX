"""Main bot logic for DOGE funding rate monitoring."""

import logging
import time
from datetime import datetime
from typing import Optional

from okx_client import OKXClient
from config import Config

logger = logging.getLogger(__name__)


class FundingBot:
    """Bot for monitoring DOGE funding rates on OKX."""

    def __init__(self):
        """Initialize the funding bot."""
        self.client = OKXClient(
            api_key=Config.OKX_API_KEY,
            secret=Config.OKX_SECRET_KEY,
            passphrase=Config.OKX_PASSPHRASE,
            demo_mode=Config.DEMO_MODE
        )
        self.symbol = Config.SYMBOL
        self.check_interval = Config.CHECK_INTERVAL
        self.funding_threshold = Config.FUNDING_THRESHOLD
        self.running = False

        mode_str = " (DEMO MODE)" if Config.DEMO_MODE else ""
        logger.info(f"FundingBot initialized for {self.symbol}{mode_str}")
        logger.info(f"Check interval: {self.check_interval}s, Threshold: {self.funding_threshold * 100}%")

    def check_funding_rate(self) -> Optional[float]:
        """
        Check current funding rate.

        Returns:
            Current funding rate or None on error
        """
        funding_data = self.client.get_funding_rate(self.symbol)

        if funding_data:
            funding_rate = funding_data.get('fundingRate')
            next_funding_time = funding_data.get('nextFundingTime')

            if funding_rate is not None:
                funding_rate_percent = funding_rate * 100

                # Format timestamp
                time_str = 'N/A'
                if next_funding_time:
                    dt = datetime.fromtimestamp(next_funding_time / 1000)
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S')

                logger.info(f"Current funding rate: {funding_rate_percent:.4f}% (Next: {time_str})")

                # Check if threshold exceeded
                if abs(funding_rate) >= self.funding_threshold:
                    self._alert_high_funding(funding_rate_percent, time_str)

                return funding_rate

        return None

    def _alert_high_funding(self, rate_percent: float, next_time: str):
        """
        Alert when funding rate exceeds threshold.

        Args:
            rate_percent: Funding rate in percentage
            next_time: Next funding time
        """
        if rate_percent > 0:
            logger.warning(f"⚠️  HIGH POSITIVE FUNDING RATE: {rate_percent:.4f}%")
            logger.warning(f"   Longs paying shorts | Next funding: {next_time}")
        else:
            logger.warning(f"⚠️  HIGH NEGATIVE FUNDING RATE: {rate_percent:.4f}%")
            logger.warning(f"   Shorts paying longs | Next funding: {next_time}")

    def get_market_info(self):
        """Get and display current market information."""
        ticker = self.client.get_ticker(self.symbol)

        if ticker:
            last_price = ticker.get('last', 'N/A')
            bid = ticker.get('bid', 'N/A')
            ask = ticker.get('ask', 'N/A')
            volume_24h = ticker.get('volCcy24h', 'N/A')

            logger.info(f"Market Info for {self.symbol}:")
            logger.info(f"  Last Price: {last_price}")
            logger.info(f"  Bid/Ask: {bid}/{ask}")
            logger.info(f"  24h Volume: {volume_24h}")

    def display_funding_history(self, limit: int = 5):
        """
        Display historical funding rates.

        Args:
            limit: Number of historical records to display
        """
        history = self.client.get_funding_history(self.symbol, limit=limit)

        if history:
            logger.info(f"\nFunding Rate History (Last {len(history)} periods):")
            logger.info("-" * 60)
            for record in history:
                rate = record.get('fundingRate', 0) * 100
                funding_time = record.get('fundingTime', 0)
                dt = datetime.fromtimestamp(funding_time / 1000)
                time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                logger.info(f"  {time_str}: {rate:+.4f}%")
            logger.info("-" * 60)

    def run_once(self):
        """Run a single check cycle."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Checking funding rate at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")

        self.get_market_info()
        self.check_funding_rate()

    def run(self):
        """Run the bot continuously."""
        self.running = True
        logger.info("Starting DOGE Funding Rate Bot...")
        logger.info(f"Monitoring {self.symbol} every {self.check_interval} seconds")

        # Display initial funding history
        self.display_funding_history()

        try:
            while self.running:
                self.run_once()

                logger.info(f"\nNext check in {self.check_interval} seconds...")
                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            logger.info("\nBot stopped by user")
            self.running = False
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            self.running = False

    def stop(self):
        """Stop the bot."""
        self.running = False
        logger.info("Bot stopping...")
