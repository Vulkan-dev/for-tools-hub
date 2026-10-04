"""NopeCHA CAPTCHA solving (https://developers.nopecha.com).

Extracted from the control panel's ``nopecha`` module. Talks to the documented
v1 API (``/v1/status`` and ``/v1/token/<service>``) with automatic fallback to
the legacy ``/token/`` endpoint, and is wired into ``discord.py-self`` through
the ``captcha_handler`` hook so join challenges are solved automatically
instead of crashing the run.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import aiohttp

from . import config, logger

log = logger.Logger("nopecha")

DEFAULT_POLL_INTERVAL = 1.0  # NopeCHA recommends >= 500ms between polls
DEFAULT_TIMEOUT = 180
MAX_ATTEMPTS = 6  # retries for 429 / 5xx / network failures

# App codes from https://nopecha.com/api-reference
_CODE_UNKNOWN = 9
_CODE_INVALID_REQUEST = 10
_CODE_RATE_LIMITED = 11
_CODE_BANNED_IP = 12
_CODE_INCOMPLETE = 14
_CODE_INVALID_KEY = 15
_CODE_OUT_OF_CREDIT = 16
_CODE_UNAVAILABLE_FEATURE = 18

_V1_UNAVAILABLE = (404, 405, 501)


class NopechaError(RuntimeError):
    """Raised when the NopeCHA API rejects or fails a job."""


def captcha_url() -> str:
    return str(config.get("captcha_url") or "https://discord.com/channels/@me")


def _base_url() -> str:
    base = str(config.get("nopecha_url") or "https://api.nopecha.com").strip().rstrip('/')
    if base.endswith('/token'):  # tolerate the old default endpoint
        base = base[: -len('/token')]
    return base or 'https://api.nopecha.com'


def _get_key(key: Optional[str] = None) -> str:
    resolved = (key or str(config.get("nopecha_key") or '')).strip()
    if not resolved:
        raise NopechaError(
            'No NopeCHA key - set "nopecha_key" in config.json or NOPECHA_KEY.'
        )
    return resolved


def _parse(raw: str) -> Optional[dict]:
    try:
        body = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def _code(body: Optional[dict]) -> Optional[int]:
    if not isinstance(body, dict):
        return None
    value = body.get('code', body.get('error'))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _describe(status: int, body: Optional[dict]) -> str:
    """Turn an error response into an actionable message."""
    message = body.get('message') if isinstance(body, dict) else None
    code = _code(body)
    if status == 401 or code == _CODE_INVALID_KEY:
        return 'invalid API key - check nopecha_key in config.json'
    if code == _CODE_OUT_OF_CREDIT:
        return 'out of credit - top up at https://nopecha.com'
    if code == _CODE_BANNED_IP:
        return 'this IP is not eligible for the NopeCHA free plan'
    if status == 402 or code == _CODE_UNAVAILABLE_FEATURE:
        return 'plan does not include this feature - renew at https://nopecha.com'
    if status == 400 or code == _CODE_INVALID_REQUEST:
        return f'invalid request: {message or body!r}'
    if status == 429 or code == _CODE_RATE_LIMITED:
        return 'rate limited - slow down and retry'
    if (status and status >= 500) or code == _CODE_UNKNOWN:
        detail = message or f'HTTP {status}'
        return f'NopeCHA server error: {detail}'
    if message:
        return f'{message} (HTTP {status})'
    return f'NopeCHA HTTP {status}: {body!r}'


async def _request(session: aiohttp.ClientSession, method: str, url: str, *,
                   key: str, params: Optional[dict] = None,
                   body: Optional[dict] = None) -> tuple[int, Optional[dict]]:
    """Perform one API call, retrying rate limits, 5xx and network errors."""
    query = {'key': key}
    if params:
        query.update(params)
    headers = {'Authorization': f'Basic {key}', 'Content-Type': 'application/json'}
    delay = 1.0
    for attempt in range(MAX_ATTEMPTS):
        retry_after: Optional[str] = None
        try:
            async with session.request(
                method, url, params=query, headers=headers, json=body
            ) as resp:
                status = resp.status
                raw = await resp.text()
                retry_after = resp.headers.get('Retry-After')
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            if attempt == MAX_ATTEMPTS - 1:
                raise NopechaError(f'NopeCHA request failed: {err}')
            await asyncio.sleep(delay)
            delay = min(delay * 2, 8)
            continue

        parsed = _parse(raw)
        if status == 429 or status >= 500:
            if attempt == MAX_ATTEMPTS - 1:
                return status, parsed
            try:
                wait = float(retry_after) if retry_after else delay
            except (TypeError, ValueError):
                wait = delay
            await asyncio.sleep(max(wait, 0.5))
            delay = min(delay * 2, 8)
            continue
        return status, parsed

    raise NopechaError('NopeCHA request failed')


async def get_status(key: Optional[str] = None) -> dict:
    """Return the NopeCHA subscription status (plan / credits / expiry)."""
    resolved = _get_key(key)
    base = _base_url()
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        status, body = await _request(session, 'GET', f'{base}/v1/status', key=resolved)
        if status in _V1_UNAVAILABLE:
            status, body = await _request(
                session, 'GET', f'{base}/status/', key=resolved
            )
    if status != 200 or not isinstance(body, dict) or 'error' in body or 'code' in body:
        raise NopechaError(_describe(status, body))
    return body


async def _solve(job_type: str, key: str, *, sitekey: str, url: str,
                 data: Optional[dict[str, Any]] = None,
                 useragent: Optional[str] = None,
                 payload_extra: Optional[dict[str, Any]] = None,
                 timeout: float = DEFAULT_TIMEOUT,
                 poll_interval: float = DEFAULT_POLL_INTERVAL) -> str:
    if not sitekey:
        raise NopechaError('NopeCHA solve requires a sitekey')

    base = _base_url()
    token_url = f'{base}/v1/token/{job_type}'
    payload: dict[str, Any] = {'sitekey': sitekey, 'url': url}
    if data:
        payload['data'] = data
    if useragent:
        payload['useragent'] = useragent
    if payload_extra:
        payload.update(payload_extra)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout)
    ) as session:
        status, body = await _request(
            session, 'POST', token_url, key=key, body=payload
        )
        if status in _V1_UNAVAILABLE:
            log.warning('NopeCHA v1 endpoint unavailable (HTTP %s), '
                        'falling back to the legacy /token/ endpoint', status)
            token_url = f'{base}/token/'
            status, body = await _request(
                session, 'POST', token_url, key=key,
                body={'type': job_type, **payload},
            )

        job_id = body.get('data') if isinstance(body, dict) else None
        if status != 200 or not isinstance(job_id, str) or not job_id:
            raise NopechaError(f'NopeCHA submit failed: {_describe(status, body)}')

        while loop.time() < deadline:
            await asyncio.sleep(poll_interval)
            status, body = await _request(
                session, 'GET', token_url, key=key, params={'id': job_id}
            )
            if status == 200 and isinstance(body, dict):
                solution = body.get('data')
                if isinstance(solution, str) and solution:
                    return solution
            if status == 409 or _code(body) == _CODE_INCOMPLETE:
                continue  # still solving
            if status == 429 or (status and status >= 500):
                continue  # already retried inside _request; keep waiting
            raise NopechaError(f'NopeCHA job failed: {_describe(status, body)}')

    raise NopechaError('NopeCHA timed out waiting for a solution')


async def solve_hcaptcha(sitekey: str, url: Optional[str] = None,
                         rqdata: Optional[str] = None,
                         useragent: Optional[str] = None,
                         key: Optional[str] = None,
                         timeout: float = DEFAULT_TIMEOUT) -> str:
    """Solve an hCaptcha challenge (Discord uses hCaptcha for its checks)."""
    data = {'rqdata': rqdata} if rqdata else None
    return await _solve(
        'hcaptcha',
        _get_key(key),
        sitekey=sitekey,
        url=url or captcha_url(),
        data=data,
        useragent=useragent,
        timeout=timeout,
    )


async def solve_recaptcha(sitekey: str, url: Optional[str] = None,
                          rqdata: Optional[str] = None,
                          useragent: Optional[str] = None,
                          key: Optional[str] = None,
                          timeout: float = DEFAULT_TIMEOUT) -> str:
    """Solve a reCAPTCHA challenge (fallback service used by Discord)."""
    data = {'rqdata': rqdata} if rqdata else None
    return await _solve(
        'recaptcha2',
        _get_key(key),
        sitekey=sitekey,
        url=url or captcha_url(),
        data=data,
        useragent=useragent,
        timeout=timeout,
    )


async def discord_captcha_handler(exception, client) -> str:
    """``discord.py-self`` captcha hook: ``async (CaptchaRequired, Client) -> str``."""
    if not _get_key_or_none():
        log.error('No NopeCHA key, cannot solve CAPTCHA: %s',
                  getattr(exception, 'errors', None))
        raise exception

    service = (getattr(exception, 'service', None) or 'recaptcha').lower()
    # ``CaptchaRequired.sitekey`` falls back to a reCAPTCHA key, so take the
    # sitekey Discord actually sent for hCaptcha instead of trusting it.
    raw_sitekey = getattr(exception, '_sitekey', None)
    rqdata = getattr(exception, 'rqdata', None)

    http = getattr(client, 'http', None)
    useragent = getattr(http, 'user_agent', None) if http else None

    log.warning('Solving %s CAPTCHA (sitekey=%s) ...', service, raw_sitekey)

    if 'hcaptcha' in service:
        if not raw_sitekey:
            log.error('hCaptcha challenge came without a sitekey '
                      '(service=%s) - cannot solve it', service)
            raise exception
        token = await solve_hcaptcha(
            sitekey=raw_sitekey,
            url=captcha_url(),
            rqdata=rqdata,
            useragent=useragent,
        )
    elif 'recaptcha' in service:
        token = await solve_recaptcha(
            sitekey=exception.sitekey,
            url=captcha_url(),
            rqdata=rqdata,
            useragent=useragent,
        )
    else:
        log.error('Unsupported CAPTCHA service: %s', service)
        raise exception

    log.info('CAPTCHA solved (%d chars)', len(token))
    return token


def _get_key_or_none() -> Optional[str]:
    try:
        return _get_key()
    except NopechaError:
        return None


async def log_status() -> None:
    """Log the subscription status at startup so expired keys are obvious."""
    if not _get_key_or_none():
        log.warning('No NopeCHA key set - CAPTCHA challenges will fail')
        return
    try:
        status = await get_status()
    except NopechaError as err:
        log.warning('Status check failed: %s', err)
        return
    except Exception as err:
        log.warning('Could not reach the status API: %s', err)
        return

    state = str(status.get('status', 'unknown'))
    if state.lower() != 'active':
        log.warning(
            'Subscription is "%s" (plan=%s, credits=%s) - renew at https://nopecha.com '
            'or Discord CAPTCHAs will not be solved',
            state, status.get('plan'), status.get('credit'),
        )
    else:
        log.info('Subscription active (plan=%s, credits=%s)',
                 status.get('plan'), status.get('credit'))
