"""Configuration constants for DOGE carry trading bot."""

import os

# Trading Safety Parameters
BALANCE_BUFFER_RATIO = 0.92  # Keep 8% buffer for fees and margin
BALANCE_CHECK_BUFFER = 0.95  # Safety buffer for balance checks
POSITION_REDUCTION_FACTOR = 0.9  # Reduce position to 90% if balance insufficient

# Margin Requirements
MARGIN_REQUIREMENT_ESTIMATE = 0.15  # Conservative 15% margin requirement for perp
MARGIN_SAFETY_BUFFER = 2.0  # 2x buffer for margin checks
REBALANCE_MARGIN_BUFFER = 3.0  # 3x safety buffer for rebalancing

# Leverage and Loan Parameters
DEFAULT_TARGET_MULTIPLIER = 1.5  # 1.5x leverage (was 2.0 - TOO RISKY!)
DEFAULT_SAFETY_FACTOR = 0.75  # Use 75% of available loan quota
FALLBACK_MULTIPLIER = 1.2  # Even more conservative fallback
FALLBACK_SAFETY_FACTOR = 0.6

# Thresholds
LIQUIDATION_THRESHOLD = float(os.getenv("LIQ_THRESHOLD", "0.01"))  # 1% (was 0.2% - TOO LOW!)
FUNDING_FLIP_THRESHOLD = 0.00001  # Close positions if funding flips
APR_EXIT_THRESHOLD = 0.08  # Exit if APR > 8%
RISK_RATIO_WARNING = 0.9  # Warn if risk ratio > 90%
RISK_RATIO_DELEVER = 0.80  # De-leverage if risk ratio > 80%
REBALANCE_DELTA_THRESHOLD = 0.01  # Rebalance if delta > 1%

# Position Management
DELEVER_CUT_RATIO = 0.30  # Sell 30% of position when de-leveraging
MIN_POSITION_SIZE = 0.001  # Minimum position size to avoid zero division
REBALANCE_THRESHOLD_MULTIPLIER = 0.5  # Close >50% triggers full reset

# Timeouts and Intervals
APR_POLL_INTERVAL = 600  # 10 minutes
REBALANCE_LOOP_INTERVAL = 60  # 1 minute
PNL_GUARD_INTERVAL = 300  # 5 minutes
PNL_STOP_THRESHOLD = 0.02  # Stop if 2% drop in 24h
EQUITY_REF_RESET_INTERVAL = 86400  # 24 hours

# Retry Configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_INITIAL_DELAY = 1.0  # seconds
RETRY_MAX_DELAY = 10.0  # seconds
RETRY_BACKOFF_MULTIPLIER = 2.0

# Minimum Loan Amounts
MIN_LOAN_AMOUNT = 1.0  # Minimum $1 USDT loan
MIN_REPAY_AMOUNT = 1.0  # Minimum $1 USDT repayment
