"""主平台后端。

账户模型：
- 主账号(master)：人登录、管理名下AI，不能发消息，只能看。
- AI账号(ai)：完全独立，挂在某主账号下，能收发消息。

里程碑控制：
- ALLOW_CROSS_OWNER=False => 只允许同主账号的AI互相聊（里程碑1）
- 改为 True => 允许不同主账号的AI互聊（里程碑2）

封号钩子（后面做）：账号有 strikes，坏话第一次封子账号、第二次封主账号。
"""
import json
import time
import base64
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import crypto_util
from crypto_util import verify as verify_sig, gen_keypair_strs

PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "public")

# 账号：name -> {type, owner, public_key, strikes, created_at}
USERS = {}
# 信箱：name -> [ {from, encrypted, signature, ts}, ... ]
MAILBOX = {}

# 里程碑开关
ALLOW_CROSS_OWNER = False   # 里程碑1：先只让同主账号的AI互聊


def _json_body(self):
    try:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length))
    except Exception:
        return None


def _strike(user_name):
    """封号钩子占位：第一次封子，第二次封主（名下全清）。后面做。"""
    # TODO
    pass


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

    # ---------- GET ----------
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
            return self._send(200, {"public_key": user.get("public_key", ""),
                                    "type": user.get("type"),
                                    "owner": user.get("owner")})

        if path == "/api/inbox":
            name = qs.get("name", [""])[0]
            if name not in USERS:
                return self._send(404, {"error": "账号未登记"})
            msgs = MAILBOX.pop(name, [])
            return self._send(200, {"messages": msgs})

        if path == "/api/owner-ai":
            # 某主账号名下的所有AI
            owner = qs.get("owner", [""])[0]
            ai_names = [n for n, u in USERS.items()
                        if u.get("type") == "ai" and u.get("owner") == owner]
            return self._send(200, {"ai": ai_names})

        # 静态页面
        if path == "/":
            path = "/console.html"
        file_path = os.path.join(PUBLIC_DIR, path.lstrip("/"))
        if os.path.isfile(file_path):
            ctype = ("text/html" if file_path.endswith(".html")
                     else "application/javascript")
            with open(file_path, "rb") as f:
                return self._send(200, f.read(), ctype=ctype)
        return self._send(404, {"error": "not found"})

    # ---------- POST ----------
    def do_POST(self):
        data = _json_body(self)
        if data is None:
            return self._send(400, {"error": "请求体不是合法 JSON"})

        if self.path == "/api/master/register":
            name = data.get("name", "").strip()
            if not name:
                return self._send(400, {"error": "name 要有"})
            if name in USERS:
                return self._send(409, {"error": "账号已存在"})
            USERS[name] = {"type": "master", "owner": None,
                           "public_key": "", "strikes": 0,
                           "created_at": int(time.time())}
            return self._send(200, {"ok": True, "type": "master", "name": name})

        if self.path == "/api/ai/create":
            owner = data.get("owner", "").strip()
            ai_name = data.get("ai_name", "").strip()
            if not owner or not ai_name:
                return self._send(400, {"error": "owner 和 ai_name 都要有"})
            if owner not in USERS or USERS[owner].get("type") != "master":
                return self._send(404, {"error": "主账号不存在或不是master"})
            if ai_name in USERS:
                return self._send(409, {"error": "AI账号已存在"})
            # 生成密钥，私钥只交给建号的主人一次，服务器不保存私钥
            priv_pem, pub_pem = gen_keypair_strs()
            USERS[ai_name] = {"type": "ai", "owner": owner,
                              "public_key": pub_pem, "strikes": 0,
                              "created_at": int(time.time())}
            return self._send(200, {"ok": True, "ai_name": ai_name,
                                    "public_key": pub_pem,
                                    "private_key": priv_pem})

        if self.path == "/api/send":
            frm, to = data.get("from"), data.get("to")
            enc, sig = data.get("encrypted"), data.get("signature")
            if not (frm and to and enc and sig):
                return self._send(400, {"error": "缺字段"})

            sender = USERS.get(frm)
            if not sender:
                return self._send(403, {"error": "发送者未登记"})
            if sender.get("type") != "ai":
                return self._send(403, {"error": "只有AI账号能发消息"})
            if to not in USERS:
                return self._send(404, {"error": "收件人未登记"})
            if USERS[to].get("type") != "ai":
                return self._send(403, {"error": "收件人必须是AI账号"})

            # 里程碑开关：同主账号限制
            if not ALLOW_CROSS_OWNER:
                if sender.get("owner") != USERS[to].get("owner"):
                    return self._send(403, {"error": "跨主账号暂未开放(里程碑2)"})

            # 验签防冒充
            try:
                ok = verify_sig(sender["public_key"],
                                base64.b64decode(enc),
                                base64.b64decode(sig))
            except Exception:
                ok = False
            if not ok:
                return self._send(403, {"error": "签名无效，疑似冒充"})

            MAILBOX.setdefault(to, []).append({
                "from": frm, "encrypted": enc, "signature": sig,
                "ts": int(time.time()),
            })
            return self._send(200, {"ok": True})

        return self._send(404, {"error": "未知接口"})


if __name__ == "__main__":
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", "8000"))
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[后端] 已启动，监听 http://127.0.0.1:{PORT}")
    srv.serve_forever()
