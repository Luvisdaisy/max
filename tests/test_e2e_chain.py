from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from max_gui.app import MaxGuiApp
from max_gui.config import Settings
from max_gui.widgets.prompt import PromptInput


def _start_stub() -> tuple[ThreadingHTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.startswith("/v1/models"):
                body = json.dumps({"data": [{"id": "qwen3.5-2b"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            _ = self.rfile.read(length)
            chunks = [
                {"choices": [{"delta": {"content": "链路"}, "finish_reason": None}]},
                {"choices": [{"delta": {"content": "通了"}, "finish_reason": None}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            ]
            payload = (
                "".join(f"data: {json.dumps(item)}\n\n" for item in chunks) + "data: [DONE]\n\n"
            )
            raw = payload.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}/v1"


async def test_enter_to_session_json_via_stub(settings: Settings) -> None:
    server, base_url = _start_stub()
    try:
        settings.base_url = base_url
        app = MaxGuiApp(settings, force_new=True)
        async with app.run_test() as pilot:
            prompt = app.query_one(PromptInput)
            prompt.text = "链路测试"
            await pilot.press("enter")
            for _ in range(40):
                await pilot.pause()
                if not app._turn_active:
                    break
            assert app.session is not None
            loaded = app.store.get(app.session.id)
            assert loaded is not None
            texts = [str(msg.content.get("text") or "") for msg in loaded.messages]
            assert any("链路测试" in text for text in texts)
            assert any("链路通了" in text for text in texts)
            assert (settings.sessions_dir / f"{loaded.id}.json").is_file()
    finally:
        server.shutdown()
