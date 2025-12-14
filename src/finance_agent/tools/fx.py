from __future__ import annotations
import requests

"""
Live FX rates using a public API.
Volatile data → NOT stored in memory.
"""
"""
Live FX rates using Frankfurter (no API key).
Tries multiple base URLs (some deployments differ).
"""


import requests

BASE_URLS = [
    "https://api.frankfurter.app",      # widely used
    "https://api.frankfurter.dev/v1",   # some deployments use /v1
    "https://api.frankfurter.dev",      # fallback
]


def _get_json(path: str, params: dict) -> dict:
    last_err = None
    for base in BASE_URLS:
        url = f"{base}{path}"
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"FX API failed for all endpoints. Last error: {last_err}")


def get_supported_currencies() -> set[str]:
    """
    Returns available 3-letter currency codes, e.g. {"GBP","USD","EUR"}.
    """
    data = _get_json("/currencies", params={})
    # Frankfurter returns { "USD": "United States Dollar", ... }
    return set(data.keys())


def get_fx_rate(base: str, target: str) -> float:
    base = base.upper()
    target = target.upper()

    data = _get_json("/latest", params={"from": base, "to": target})
    return float(data["rates"][target])


def convert(amount: float, base: str, target: str) -> float:
    rate = get_fx_rate(base, target)
    return round(amount * rate, 2)
