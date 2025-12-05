import datetime
import logging
from decimal import Decimal, ROUND_HALF_UP

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

CACHE_KEY = "gem_rates_daily"
CACHE_TTL = 60 * 60 * 20  # 20 hours
DEFAULT_CURRENCIES = ["USD", "INR", "EUR", "GBP", "AUD", "CAD", "AED", "SGD"]


def _safe_decimal(value):
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _fetch_rates_from_api(targets):
    api_key = getattr(settings, "FX_API_KEY", "") or ""
    base_url = "https://www.alphavantage.co/query"
    rates = {"USD": Decimal("1")}
    for curr in targets:
        if curr == "USD":
            continue
        try:
            resp = requests.get(
                base_url,
                params={
                    "function": "CURRENCY_EXCHANGE_RATE",
                    "from_currency": "USD",
                    "to_currency": curr,
                    "apikey": api_key,
                },
                timeout=10,
            )
            data = resp.json() if resp else {}
            quote = data.get("Realtime Currency Exchange Rate", {}) if isinstance(data, dict) else {}
            raw_rate = quote.get("5. Exchange Rate")
            rate_val = _safe_decimal(raw_rate)
            if rate_val is not None and rate_val > 0:
                rates[curr] = rate_val
        except Exception as exc:
            logger.warning("FX fetch failed for %s: %s", curr, exc)
    return rates


def _compute_gem_prices(rates, gem_usd):
    prices = {}
    for curr, rate in rates.items():
        try:
            prices[curr] = (gem_usd * rate).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        except Exception:
            continue
    return prices


def get_gem_rates(currencies=None):
    """Return cached gem pricing snapshot."""
    cached = cache.get(CACHE_KEY)
    if cached:
        return cached

    target_currencies = currencies or DEFAULT_CURRENCIES
    rates = _fetch_rates_from_api(target_currencies)
    gem_usd = Decimal("0.9")  # 90% of $1
    prices = _compute_gem_prices(rates, gem_usd)
    snapshot = {
        "base_currency": "USD",
        "gem_price_usd": str(gem_usd),
        "rates": {k: str(v) for k, v in rates.items()},
        "prices": {k: str(v) for k, v in prices.items()},
        "currencies": target_currencies,
        "fetched_at": timezone.now().isoformat(),
    }
    cache.set(CACHE_KEY, snapshot, CACHE_TTL)
    return snapshot
