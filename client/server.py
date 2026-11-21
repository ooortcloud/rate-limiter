import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import CLIENT_HOST, CLIENT_PORT, MIDDLEWARE_URLS

CLIENT_DIR = Path(__file__).resolve().parent


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class ClientHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(CLIENT_DIR), **kwargs)

    def do_GET(self):
        request_path = self.path.split("?", 1)[0]
        if request_path == "/config.json":
            payload = json.dumps({"middlewareUrls": MIDDLEWARE_URLS}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        super().do_GET()


def main() -> None:
    server = ReusableThreadingHTTPServer((CLIENT_HOST, CLIENT_PORT), ClientHandler)
    print(f"[CLIENT] 정적 서버 기동: http://{CLIENT_HOST}:{CLIENT_PORT}", flush=True)
    print(f"[CLIENT] 동적 연결 대상 미들웨어: {MIDDLEWARE_URLS}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[CLIENT] 클라이언트 서버를 종료합니다.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()