import httpx
import json
import websockets
import asyncio
import structlog
from datetime import datetime, timezone
import os
import base64
import hashlib
import hmac
from typing import Any, AsyncGenerator, Dict
import urllib.parse


def _timestamp() -> str:
    """Return current time in RFC3339 format with milliseconds."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
from ..alerts.telegram import tg
from ..utils import safe_float

log = structlog.get_logger()
OKX_HOST = "https://www.okx.com"

def _sign(ts: str, method: str, path: str, body: str, secret: str) -> str:
    prehash = f"{ts}{method}{path}{body}"
    return base64.b64encode(
        hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).digest()
    ).decode()

# ---------- helpers ----------
def _join_path(path: str, params: dict | None) -> str:
    """
    Склеивает path с query-строкой, если переданы params.
    Нужно, чтобы в подпись попадали и параметры запроса.
    """
    if not params:
        return path
    return f"{path}?{urllib.parse.urlencode(params, safe=',')}"

class OKXGateway:
    def __init__(self):
        self.key = os.getenv("OKX_KEY")
        self.secret = os.getenv("OKX_SECRET")
        self.passph = os.getenv("OKX_PASS")
        missing = [
            name
            for name, val in (
                ("OKX_KEY", self.key),
                ("OKX_SECRET", self.secret),
                ("OKX_PASS", self.passph),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"Missing OKX credentials: {', '.join(missing)}"
            )
        self.sim = os.getenv("OKX_SIM", "1") == "1"
        self.rest = httpx.AsyncClient(
            base_url=OKX_HOST,
            timeout=10.0,
            http2=True,
        )
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/private"
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._ws_logged = False

    async def close(self):
        """Close HTTP client and WebSocket connections."""
        if self.rest:
            await self.rest.aclose()
        if self._ws:
            await self._ws.close()
            self._ws = None
            self._ws_logged = False

    async def _ensure_ws(self):
        """Open and login to WebSocket if needed."""
        if not (self._ws and self._ws.open):
            self._ws = None
            await self.ws()
        if not self._ws_logged:
            await self._ws_login()

    async def _reset_ws(self, backoff_delay: float = 1.0):
        if self._ws:
            await self._ws.close()
        self._ws = None
        self._ws_logged = False
        await asyncio.sleep(backoff_delay)
        await self._ensure_ws()

    async def _headers(
        self, method: str, path: str, body: str = ""
    ) -> Dict[str, str]:
        ts = _timestamp()
        sig = _sign(ts, method, path, body, self.secret)
        hdr = {
            "OK-ACCESS-KEY": self.key,
            "OK-ACCESS-SIGN": sig,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.passph,
            "Content-Type": "application/json",
        }
        if self.sim:
            hdr["x-simulated-trading"] = "1"
        return hdr

    async def get(self, path: str, params: dict | None = None) -> Any:
        full = _join_path(path, params)
        hdr  = await self._headers("GET", full)
        r    = await self.rest.get(full, headers=hdr)
        r.raise_for_status()
        return r.json()["data"]

    async def get_equity(self) -> float:
        data = await self.get("/api/v5/account/balance", {"ccy": "USDT"})
        return float(data[0]["totalEq"])

    async def get_max_size(self, inst_id: str, td_mode: str = "cash") -> dict | None:
        """Return maximum allowed size for a new order."""
        try:
            data = await self.get(
                "/api/v5/account/max-size",
                {"instId": inst_id, "tdMode": td_mode},
            )
            if data:
                d = data[0]
                return {
                    "maxBuy": safe_float(d.get("maxBuy") or d.get("maxSize")),
                    "maxSell": safe_float(d.get("maxSell") or d.get("maxSize")),
                }
        except Exception as e:
            log.error("MAX_SIZE_ERROR", inst=inst_id, exc_info=e)
        return None

    async def get_max_avail_size(self, inst_id: str, td_mode: str = "cash") -> dict | None:
        """Return maximum available size that can be bought/sold."""
        try:
            data = await self.get(
                "/api/v5/account/max-avail-size",
                {"instId": inst_id, "tdMode": td_mode},
            )
            if data:
                d = data[0]
                return {
                    "availBuy": safe_float(d.get("availBuy")),
                    "availSell": safe_float(d.get("availSell")),
                }
        except Exception as e:
            log.error("MAX_AVAIL_ERROR", inst=inst_id, exc_info=e)
        return None

    async def post(self, path: str, payload: dict) -> Any:
        body = json.dumps(payload, separators=(",", ":"))
        hdr = await self._headers("POST", path, body)
        r = await self.rest.post(path, headers=hdr, content=body)
        r.raise_for_status()
        resp = r.json()
        if resp.get("code") != "0":
            log.warning(
                "API_ERROR",
                path=path,
                code=resp.get("code"),
                msg=resp.get("msg"),
            )
        for item in resp.get("data", []):
            if item.get("sCode") == "51000":
                await tg.send(f"⚠️ order rejected {item.get('sMsg')}")
                log.warning(
                    "ORDER_REJECTED",
                    code="51000",
                    msg=item.get("sMsg"),
                )
            elif item.get("sCode") == "51008":
                await tg.send(f"💰 Insufficient balance: {item.get('sMsg')}")
                log.warning(
                    "INSUFFICIENT_BALANCE",
                    code="51008",
                    msg=item.get("sMsg"),
                )
        return resp.get("data", [])

    async def post_order(self, payload: dict) -> Any:
        """Submit trade order and ensure success."""
        try:
            data = await self.post("/api/v5/trade/order", payload)
        except httpx.HTTPStatusError as e:
            await tg.send(f"❌ Order rejected: {e.response.text[:120]}")
            raise
        if not data or data[0].get("sCode") != "0":
            await tg.send(f"❌ Order failed: {data}")
            raise RuntimeError("orderRejected")
        return data

    # ----------  WebSocket ----------
    async def ws(self) -> websockets.WebSocketClientProtocol:
        if self._ws and self._ws.open:
            return self._ws
        # WebSocket connections don't need HTTP headers for authentication
        self._ws = await websockets.connect(
            self.ws_url,
            ping_interval=15,
            ping_timeout=15,
            max_size=2**20,
        )
        log.info("WS_CONNECTED")
        return self._ws

    async def ws_send(self, msg: dict):
        ws = await self.ws()
        await ws.send(json.dumps(msg))

    async def _ws_login(self):
        if self._ws_logged:
            return
        ts = _timestamp()
        sign = _sign(ts, "GET", "/users/self/verify", "", self.secret)
        await self.ws_send({
            "op": "login",
            "args": [{
                "apiKey": self.key,
                "passphrase": self.passph,
                "timestamp": ts,
                "sign": sign,
            }],
        })
        ws = await self.ws()
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            resp = json.loads(raw)
            if resp.get("event") == "login" and resp.get("code") == "0":
                self._ws_logged = True
                log.info("WS_LOGGED")
            else:
                log.error("WS_LOGIN_FAIL", data=resp)
        except Exception as e:
            log.error("WS_LOGIN_ERR", exc_info=e)

    async def ws_private_stream(
        self, channel: str, inst_id: str | None = None
    ) -> AsyncGenerator[dict, None]:
        sub_arg = {"channel": channel}
        if inst_id:
            sub_arg["instId"] = inst_id
        await self._ensure_ws()
        await self.ws_send({"op": "subscribe", "args": [sub_arg]})
        
        reconnect_delay = 1.0
        max_delay = 60.0
        
        while True:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), 30)
                # Reset delay on successful message
                reconnect_delay = 1.0
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                log.warning("WS_TIMEOUT", chan=channel, delay=reconnect_delay)
                await self._reset_ws(reconnect_delay)
                await self.ws_send({"op": "subscribe", "args": [sub_arg]})
                reconnect_delay = min(reconnect_delay * 2, max_delay)
                continue
            except Exception as e:
                log.error("WS_STREAM_ERR", exc_info=e, delay=reconnect_delay)
                await self._reset_ws(reconnect_delay)
                await self.ws_send({"op": "subscribe", "args": [sub_arg]})
                reconnect_delay = min(reconnect_delay * 2, max_delay)
                continue
            
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError as e:
                log.error("WS_JSON_ERR", raw=raw[:100], exc_info=e)
                continue
                
            if msg.get("event") == "error":
                log.error("WS_ERR", data=msg)
            if msg.get("arg", {}).get("channel") == channel:
                yield msg
