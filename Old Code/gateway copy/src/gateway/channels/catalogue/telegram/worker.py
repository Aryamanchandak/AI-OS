"""Supervised Telegram long-poll worker.

Run with ``python -m gateway.channels.catalogue.telegram.worker`` after
enabling Telegram and registering Gateway in ``config/services.yaml``.
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx

from gateway.channels.catalogue.telegram.adapter import Adapter
from gateway.channels.envelope import ChannelReply
from gateway.channels.runtime import get_install_token
from gateway.channels.worker import WorkerSupervisor
from gateway.platform.service_registry import gateway_address


class TelegramPoller:
    def __init__(self, gateway_url: str, token: str, bot_token: str) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.token = token
        self.bot_token = bot_token
        self.adapter = Adapter()

    async def __call__(self, stop: asyncio.Event) -> None:
        import websockets

        ws_base = self.gateway_url.replace("http://", "ws://").replace("https://", "wss://")
        uri = f"{ws_base}/v1/channels/telegram"
        offset: int | None = None
        async with (
            httpx.AsyncClient(timeout=20.0) as client,
            websockets.connect(
                uri, additional_headers={"Authorization": f"Bearer {self.token}"}
            ) as socket,
        ):
            while not stop.is_set():
                request = asyncio.create_task(client.get(
                    f"https://api.telegram.org/bot{self.bot_token}/getUpdates",
                    params={"timeout": 10, **({"offset": offset} if offset is not None else {})},
                ))
                stopping = asyncio.create_task(stop.wait())
                done, _ = await asyncio.wait((request, stopping), return_when=asyncio.FIRST_COMPLETED)
                if stopping in done:
                    request.cancel()
                    await asyncio.gather(request, return_exceptions=True)
                    return
                stopping.cancel()
                response = await request
                response.raise_for_status()
                payload = response.json()
                for update in payload.get("result", []):
                    offset = int(update["update_id"]) + 1
                    message = await self.adapter.on_message(update)
                    if message is None:
                        continue
                    await socket.send(message.model_dump_json())
                    reply_payload = json.loads(await socket.recv())
                    if "error" not in reply_payload and reply_payload.get("status") != "dropped":
                        await self.adapter.send(ChannelReply.model_validate(reply_payload))


async def run_worker() -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    poller = TelegramPoller(gateway_address().url, get_install_token(), bot_token)
    supervisor = WorkerSupervisor(initial_backoff_s=1.0, max_backoff_s=30.0)
    supervisor.register("telegram", poller, enabled=True)
    try:
        await asyncio.Event().wait()
    finally:
        await supervisor.close()


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
