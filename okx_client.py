"""OKX API client for funding rates."""

import requests
import logging
import random
import time
from typing import Dict, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class OKXClient:
    """Client for interacting with OKX API."""

    BASE_URL = "https://www.okx.com"

    def __init__(self, api_key: str = '', secret: str = '', passphrase: str = '', demo_mode: bool = False):
        """
        Initialize OKX client.

        Args:
            api_key: OKX API key (optional for public endpoints)
            secret: OKX secret key (optional for public endpoints)
            passphrase: OKX passphrase (optional for public endpoints)
            demo_mode: Use demo data instead of real API calls
        """
        self.api_key = api_key
        self.secret = secret
        self.passphrase = passphrase
        self.demo_mode = demo_mode
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })

        if demo_mode:
            logger.info("OKX client initialized in DEMO mode")
        else:
            logger.info("OKX client initialized")

    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """
        Make a request to OKX API.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            Response data or None on error
        """
        try:
            url = f"{self.BASE_URL}{endpoint}"
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get('code') == '0':
                return data.get('data', [])
            else:
                logger.error(f"API error: {data.get('msg', 'Unknown error')}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None

    def get_funding_rate(self, inst_id: str) -> Optional[Dict]:
        """
        Get current funding rate for an instrument.

        Args:
            inst_id: Instrument ID (e.g., 'DOGE-USDT-SWAP')

        Returns:
            Dictionary with funding rate data or None on error
        """
        if self.demo_mode:
            return self._get_demo_funding_rate(inst_id)

        try:
            endpoint = "/api/v5/public/funding-rate"
            params = {'instId': inst_id}

            data = self._make_request(endpoint, params)

            if data and len(data) > 0:
                rate_data = data[0]
                funding_rate = float(rate_data.get('fundingRate', 0))
                next_funding_time = int(rate_data.get('nextFundingTime', 0))

                logger.info(f"Funding rate for {inst_id}: {funding_rate}")

                return {
                    'fundingRate': funding_rate,
                    'nextFundingTime': next_funding_time,
                    'fundingTime': int(rate_data.get('fundingTime', 0)),
                    'instId': inst_id
                }
            else:
                logger.warning(f"No funding rate data for {inst_id}")
                return None

        except Exception as e:
            logger.error(f"Error fetching funding rate for {inst_id}: {e}")
            return None

    def _get_demo_funding_rate(self, inst_id: str) -> Dict:
        """Generate demo funding rate data."""
        current_time = int(time.time() * 1000)
        # Next funding in ~8 hours
        next_funding = current_time + (8 * 3600 * 1000)
        # Random funding rate between -0.01% and 0.01%
        funding_rate = random.uniform(-0.0001, 0.0001)

        return {
            'fundingRate': funding_rate,
            'nextFundingTime': next_funding,
            'fundingTime': current_time,
            'instId': inst_id
        }

    def get_ticker(self, inst_id: str) -> Optional[Dict]:
        """
        Get current ticker data for an instrument.

        Args:
            inst_id: Instrument ID (e.g., 'DOGE-USDT-SWAP')

        Returns:
            Dictionary with ticker data or None on error
        """
        if self.demo_mode:
            return self._get_demo_ticker(inst_id)

        try:
            endpoint = "/api/v5/market/ticker"
            params = {'instId': inst_id}

            data = self._make_request(endpoint, params)

            if data and len(data) > 0:
                ticker = data[0]
                return {
                    'last': float(ticker.get('last', 0)),
                    'bid': float(ticker.get('bidPx', 0)),
                    'ask': float(ticker.get('askPx', 0)),
                    'high24h': float(ticker.get('high24h', 0)),
                    'low24h': float(ticker.get('low24h', 0)),
                    'vol24h': float(ticker.get('vol24h', 0)),
                    'volCcy24h': float(ticker.get('volCcy24h', 0)),
                    'instId': inst_id
                }
            else:
                logger.warning(f"No ticker data for {inst_id}")
                return None

        except Exception as e:
            logger.error(f"Error fetching ticker for {inst_id}: {e}")
            return None

    def _get_demo_ticker(self, inst_id: str) -> Dict:
        """Generate demo ticker data."""
        base_price = 0.385  # DOGE approximate price
        spread = base_price * 0.0003  # 0.03% spread

        return {
            'last': base_price,
            'bid': base_price - spread / 2,
            'ask': base_price + spread / 2,
            'high24h': base_price * 1.05,
            'low24h': base_price * 0.95,
            'vol24h': random.uniform(1000000, 5000000),
            'volCcy24h': random.uniform(400000, 2000000),
            'instId': inst_id
        }

    def get_funding_history(self, inst_id: str, limit: int = 10) -> Optional[List[Dict]]:
        """
        Get historical funding rates.

        Args:
            inst_id: Instrument ID (e.g., 'DOGE-USDT-SWAP')
            limit: Number of historical records to fetch

        Returns:
            List of historical funding rates or None on error
        """
        if self.demo_mode:
            return self._get_demo_funding_history(inst_id, limit)

        try:
            endpoint = "/api/v5/public/funding-rate-history"
            params = {
                'instId': inst_id,
                'limit': str(limit)
            }

            data = self._make_request(endpoint, params)

            if data:
                history = []
                for record in data:
                    history.append({
                        'fundingRate': float(record.get('fundingRate', 0)),
                        'fundingTime': int(record.get('fundingTime', 0)),
                        'instId': inst_id
                    })

                logger.info(f"Fetched {len(history)} historical funding rates for {inst_id}")
                return history
            else:
                logger.warning(f"No funding history for {inst_id}")
                return None

        except Exception as e:
            logger.error(f"Error fetching funding history for {inst_id}: {e}")
            return None

    def _get_demo_funding_history(self, inst_id: str, limit: int) -> List[Dict]:
        """Generate demo funding history."""
        history = []
        current_time = int(time.time() * 1000)
        # Funding every 8 hours
        interval = 8 * 3600 * 1000

        for i in range(limit):
            funding_time = current_time - (i * interval)
            funding_rate = random.uniform(-0.0002, 0.0002)
            history.append({
                'fundingRate': funding_rate,
                'fundingTime': funding_time,
                'instId': inst_id
            })

        return history
