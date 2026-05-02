"""
IBM Cloud IAM Token Exchange — with per-key in-memory caching.

IBM watsonx.ai and watsonx Orchestrate require a short-lived Bearer token,
not the raw API key. This module exchanges the IBM Cloud API key for an IAM
access token and caches it for 55 minutes (IBM tokens expire after 60 minutes).

Usage:
    from iam_auth import get_iam_token
    token = await get_iam_token(api_key)
    headers = {"Authorization": f"Bearer {token}"}
"""

import asyncio
import time
from typing import Dict

import aiohttp

IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"

# {api_key -> {"token": str, "expires_at": float}}
_token_cache: Dict[str, dict] = {}
_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def get_iam_token(api_key: str) -> str:
    """
    Exchange an IBM Cloud API key for an IAM access token.

    The token is cached in memory and reused until 5 minutes before expiry.
    A fresh exchange is performed automatically when the token is near expiry.

    Args:
        api_key: IBM Cloud API key from WATSONX_API_KEY / ORCHESTRATE_API_KEY.

    Returns:
        IAM access token string suitable for use as a Bearer token.

    Raises:
        Exception: If the IAM exchange fails (non-200 response).
    """
    now = time.time()
    cached = _token_cache.get(api_key)
    if cached and now < cached["expires_at"]:
        return cached["token"]

    async with _get_lock():
        # Double-check after acquiring the lock — another coroutine may have
        # refreshed the token while we were waiting.
        now = time.time()
        cached = _token_cache.get(api_key)
        if cached and now < cached["expires_at"]:
            return cached["token"]

        async with aiohttp.ClientSession() as session:
            async with session.post(
                IAM_TOKEN_URL,
                data={
                    "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                    "apikey": api_key,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(
                        f"IAM token exchange failed HTTP {resp.status}: {text}"
                    )
                data = await resp.json()
                token = data["access_token"]
                expires_in = data.get("expires_in", 3600)
                # Cache and renew 5 minutes before the token actually expires.
                _token_cache[api_key] = {
                    "token": token,
                    "expires_at": now + expires_in - 300,
                }
                return token
