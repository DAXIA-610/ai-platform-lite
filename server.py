import json
import time
import base64
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import crypto_util
from crypto_util import verify as verify_sig

PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "public")

USERS = {}
MAILBOX = {}


def _json_body(self):
    try:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length))
    except Exception:
        return None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._send(204, b"")

    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/health":
            return self._send(200, {"ok": True})

        if path == "/api/public":
            name = qs.get("name", [""])[0]
            user = USERS.get(name)
            if not user:
                return self._send(404, {"error": "账号未登记"})
            return self._send(200, {"public_key": user["public_key"]})

        if path == "/api/inbox":
            name = qs.get("name", [""])[0]
            msgs = MAILBOX.pop(name, [])
            return self._send(200, {"messages": msgs})

        if path == "/":
            path = "/viewer.html"
        file_path = os.path.join(PUBLIC_DIR, path.lstrip("/"))
        if os.path.isfile(file_path):
            with open(file_path, "rb") as f:
                return self._send(200, f.read(),
                                  ctype="text/html" if file_path.endswith(".html")
                                  else "application/javascript")
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        data = _json_body(self)
        if data is None:
            return self._send(400, {"error": "请求体不是合法 JSON"})

        if self.path == "/api/register":
            name = data.get("name", "").strip()
            pub = data.get("public_key", "").strip()
            if not name or not pub:
                return self._send(400, {"error": "name 和 public_key 都要有"})
            USERS[name] = {"public_key": pub, "registered_at": int(time.time())}
            return self._send(200, {"ok": True, "name": name})

        if self.path == "/api/send":
            frm, to = data.get("from"), data.get("to")
            enc = data.get("encrypted")
            sig = data.get("signature")
            if not (frm and to and enc and sig):
                return self._send(400, {"error": "缺字段"})

            sender = USERS.get(frm)
            if not sender:
                return self._send(403, {"error": "发送者未登记"})
            if to not in USERS:
                return self._send(404, {"error": "收件人未登记"})

            try:
                ok = verify_sig(sender["public_key"],
                                base64.b64decode(enc),
                                base64.b64decode(sig))
            except Exception:
                ok = False
            if not ok:
                return self._send(403, {"error": "签名无效，疑似冒充"})

            MAILBOX.setdefault(to, []).append({
                "from": frm,
                "encrypted": enc,
                "signature": sig,
                "ts": int(time.time()),
            })
            return self._send(200, {"ok": True})

        return self._send(404, {"error": "未知接口"})


if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 8000
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[后端] 已启动，监听 http://127.0.0.1:{PORT}")
    srv.serve_forever()
