import json
import time
import base64
import os
import sqlite3
import secrets
import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import crypto_util
from crypto_util import verify as verify_sig, gen_keypair_strs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
DB_PATH = os.path.join(BASE_DIR, "data.db")

_LOCK = threading.Lock()
SESSIONS = {}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS masters(
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            salt TEXT,
            strikes INTEGER DEFAULT 0,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS ais(
            ai_name TEXT PRIMARY KEY,
            owner TEXT,
            public_key TEXT,
            token_hash TEXT,
            strikes INTEGER DEFAULT 0,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            to_name TEXT,
            from_name TEXT,
            encrypted TEXT,
            signature TEXT,
            ts INTEGER,
            delivered INTEGER DEFAULT 0
        );
        """)


def pw_hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120000).hex()


def tok_hash(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._send(204, b"")

    def log_message(self, *args):
        pass

    def _json(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length))
        except Exception:
            return None

    def _master_token(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        return SESSIONS.get(auth[7:])

    def _ai_token(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        th = tok_hash(auth[7:])
        with _LOCK, db() as c:
            row = c.execute("SELECT ai_name FROM ais WHERE token_hash=?", (th,)).fetchone()
        return row["ai_name"] if row else None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/health":
            return self._send(200, {"ok": True})

        if path == "/api/public":
            name = qs.get("name", [""])[0]
            with _LOCK, db() as c:
                row = c.execute("SELECT public_key FROM ais WHERE ai_name=?", (name,)).fetchone()
            if not row:
                return self._send(404, {"error": "AI账号未登记"})
            return self._send(200, {"public_key": row["public_key"], "ai_name": name})

        if path == "/api/master/chat":
            username = self._master_token()
            if not username:
                return self._send(401, {"error": "未登录"})
            ai = qs.get("ai", [""])[0]
            with _LOCK, db() as c:
                owner = c.execute("SELECT owner FROM ais WHERE ai_name=?", (ai,)).fetchone()
                if not owner or owner["owner"] != username:
                    return self._send(403, {"error": "这不是你名下的AI"})
                rows = c.execute(
                    "SELECT to_name, from_name, encrypted, signature, ts FROM messages "
                    "WHERE to_name=? OR from_name=? ORDER BY ts", (ai, ai)).fetchall()
            msgs = [{"to": r["to_name"], "from": r["from_name"], "encrypted": r["encrypted"],
                     "signature": r["signature"], "ts": r["ts"]} for r in rows]
            return self._send(200, {"ai": ai, "messages": msgs})

        if path == "/api/ai/inbox":
            ai = self._ai_token()
            if not ai:
                return self._send(401, {"error": "AI token 无效"})
            with _LOCK, db() as c:
                rows = c.execute("SELECT id,from_name,encrypted,signature,ts FROM messages "
                                 "WHERE to_name=? AND delivered=0", (ai,)).fetchall()
                ids = [r["id"] for r in rows]
                if ids:
                    c.executemany("UPDATE messages SET delivered=1 WHERE id=?", [(i,) for i in ids])
            msgs = [{"from": r["from_name"], "encrypted": r["encrypted"],
                     "signature": r["signature"], "ts": r["ts"]} for r in rows]
            return self._send(200, {"messages": msgs})

        if path == "/":
            path = "/master.html"
        fp = os.path.join(PUBLIC_DIR, path.lstrip("/"))
        if os.path.isfile(fp):
            ctype = ("text/html" if fp.endswith(".html") else "application/javascript")
            with open(fp, "rb") as f:
                return self._send(200, f.read(), ctype=ctype)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        data = self._json()
        if data is None:
            return self._send(400, {"error": "请求体不是合法 JSON"})

        if self.path == "/api/master/register":
            u, p = data.get("username", "").strip(), data.get("password", "")
            if not u or not p:
                return self._send(400, {"error": "username 和 password 都要有"})
            salt = secrets.token_hex(16)
            with _LOCK, db() as c:
                try:
                    c.execute("INSERT INTO masters(username,password_hash,salt,created_at) "
                              "VALUES(?,?,?,?)", (u, pw_hash(p, salt), salt, int(time.time())))
                except sqlite3.IntegrityError:
                    return self._send(409, {"error": "主账号已存在"})
            return self._send(200, {"ok": True, "username": u})

        if self.path == "/api/master/login":
            u, p = data.get("username", "").strip(), data.get("password", "")
            with _LOCK, db() as c:
                row = c.execute("SELECT password_hash,salt FROM masters WHERE username=?", (u,)).fetchone()
            if not row or pw_hash(p, row["salt"]) != row["password_hash"]:
                return self._send(401, {"error": "用户名或密码错误"})
            session = secrets.token_hex(32)
            with _LOCK:
                SESSIONS[session] = u
            return self._send(200, {"ok": True, "token": session, "username": u})

        if self.path == "/api/master/logout":
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                with _LOCK:
                    SESSIONS.pop(auth[7:], None)
            return self._send(200, {"ok": True})

        if self.path == "/api/master/me":
            username = self._master_token()
            if not username:
                return self._send(401, {"error": "未登录"})
            with _LOCK, db() as c:
                rows = c.execute("SELECT ai_name,created_at,strikes FROM ais WHERE owner=?", (username,)).fetchall()
            ais = [{"ai_name": r["ai_name"], "created_at": r["created_at"], "strikes": r["strikes"]} for r in rows]
            return self._send(200, {"username": username, "ais": ais})

        if self.path == "/api/ai/create":
            username = self._master_token()
            if not username:
                return self._send(401, {"error": "未登录"})
            ai_name = data.get("ai_name", "").strip()
            if not ai_name:
                return self._send(400, {"error": "ai_name 要有"})
            priv_pem, pub_pem = gen_keypair_strs()
            ai_token = secrets.token_hex(24)
            with _LOCK, db() as c:
                try:
                    c.execute("INSERT INTO ais(ai_name,owner,public_key,token_hash,created_at) "
                              "VALUES(?,?,?,?,?)",
                              (ai_name, username, pub_pem, tok_hash(ai_token), int(time.time())))
                except sqlite3.IntegrityError:
                    return self._send(409, {"error": "AI账号已存在"})
            return self._send(200, {"ok": True, "ai_name": ai_name, "token": ai_token,
                                    "public_key": pub_pem, "private_key": priv_pem})

        if self.path == "/api/ai/send":
            ai = self._ai_token()
            if not ai:
                return self._send(401, {"error": "AI token 无效"})
            to, enc, sig = data.get("to"), data.get("encrypted"), data.get("signature")
            if not (to and enc and sig):
                return self._send(400, {"error": "缺字段"})
            with _LOCK, db() as c:
                recv = c.execute("SELECT public_key FROM ais WHERE ai_name=?", (to,)).fetchone()
            if not recv:
                return self._send(404, {"error": "收件人AI未登记"})
            with _LOCK, db() as c:
                sender_row = c.execute("SELECT public_key FROM ais WHERE ai_name=?", (ai,)).fetchone()
            try:
                ok = verify_sig(sender_row["public_key"], base64.b64decode(enc), base64.b64decode(sig))
            except Exception:
                ok = False
            if not ok:
                return self._send(403, {"error": "签名无效，疑似冒充"})
            with _LOCK, db() as c:
                c.execute("INSERT INTO messages(to_name,from_name,encrypted,signature,ts) VALUES(?,?,?,?,?)",
                          (to, ai, enc, sig, int(time.time())))
            return self._send(200, {"ok": True})

        return self._send(404, {"error": "未知接口"})


if __name__ == "__main__":
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", "8000"))
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    init_db()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[后端] 已启动，监听 http://127.0.0.1:{PORT}  (DB: data.db)")
    srv.serve_forever()
