"""Configuration management for DOGE funding bot."""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Bot configuration."""

    # OKX API credentials
    OKX_API_KEY = os.getenv('OKX_API_KEY', '')
    OKX_SECRET_KEY = os.getenv('OKX_SECRET_KEY', '')
    OKX_PASSPHRASE = os.getenv('OKX_PASSPHRASE', '')

    # Bot settings
    SYMBOL = os.getenv('SYMBOL', 'DOGE-USDT-SWAP')
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))  # seconds
    FUNDING_THRESHOLD = float(os.getenv('FUNDING_THRESHOLD', '0.01'))  # 1%

    # Demo mode
    DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    @classmethod
    def has_api_credentials(cls):
        """Check if API credentials are configured."""
        return bool(cls.OKX_API_KEY and cls.OKX_SECRET_KEY and cls.OKX_PASSPHRASE)
