import httpx
import json
import websockets
import asyncio
import structlog
import time
import os
import base64
import hashlib
import hmac
from pydantic import BaseModel
from typing import Any, AsyncGenerator, Dict

log = structlog.get_logger()
OKX_HOST = "https://www.okx.com"

def _sign(ts: str, method: str, path: str, body: str, secret: str) -> str:
    prehash = f"{ts}{method}{path}{body}"
    return base64.b64encode(hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).digest()).decode()

class OKXGateway:
    def __init__(self):
        self.key = os.getenv("OKX_KEY")
        self.secret = os.getenv("OKX_SECRET")
        self.passph = os.getenv("OKX_PASS")
        self.sim = os.getenv("OKX_SIM", "1") == "1"
        self.rest = httpx.AsyncClient(base_url=OKX_HOST, timeout=10.0, http2=True)
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/private"
        self._ws: websockets.WebSocketClientProtocol | None = None

    async def _headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
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
        hdr = await self._headers("GET", path)
        r = await self.rest.get(path, headers=hdr, params=params)
        r.raise_for_status()
        return r.json()["data"]

    async def post(self, path: str, payload: dict) -> Any:
        body = json.dumps(payload, separators=(",", ":"))
        hdr = await self._headers("POST", path, body)
        r = await self.rest.post(path, headers=hdr, content=body)
        r.raise_for_status()
        return r.json()["data"]

    # ----------  WebSocket ----------
    async def ws(self) -> websockets.WebSocketClientProtocol:
        if self._ws and self._ws.open:
            return self._ws
        hdr = await self._headers("GET", "/ws")
        self._ws = await websockets.connect(
            self.ws_url,
            extra_headers=hdr,
            ping_interval=15,
            ping_timeout=15,
            max_size=2**20,
        )
        log.info("WS_CONNECTED")
        return self._ws

    async def ws_send(self, msg: dict):
        ws = await self.ws()
        await ws.send(json.dumps(msg))

    async def ws_private_stream(self, channel: str) -> AsyncGenerator[dict, None]:
        # subscribe once
        await self.ws_send({"op": "subscribe", "args": [{"channel": channel}]})
        ws = await self.ws()
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("event") == "error":
                log.error("WS_ERR", data=msg)
            if msg.get("arg", {}).get("channel") == channel:
                yield msg
