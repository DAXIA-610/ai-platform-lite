import asyncio
import json
import time
import base64
import os
import sqlite3
import secrets
import hashlib
from aiohttp import web

import crypto_util
from crypto_util import verify as verify_sig, gen_keypair_strs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
DB_PATH = os.path.join(BASE_DIR, "data.db")

SESSIONS = {}
WS = {}
PENDING = {}
PENDING_MAX = 200
LOCK = asyncio.Lock()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS accounts(
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            salt TEXT,
            name TEXT,
            avatar TEXT,
            public_key TEXT,
            token_hash TEXT,
            strikes INTEGER DEFAULT 0,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS friends(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            a_username TEXT,
            b_username TEXT,
            status TEXT,
            requested_by TEXT,
            created_at INTEGER,
            UNIQUE(a_username, b_username)
        );
        """)


def pw_hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120000).hex()


def tok_hash(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


def get_acc(c, username):
    return c.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()


def friend_key(u, v):
    return (u, v) if u < v else (v, u)


def human(req):
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return SESSIONS.get(auth[7:])
    return None


def ai_user(req):
    ak = req.headers.get("X-AI-Key", "")
    if not ak:
        return None
    with db() as c:
        r = c.execute("SELECT username FROM accounts WHERE token_hash=?", (tok_hash(ak),)).fetchone()
    return r["username"] if r else None


def acc_info(c, username):
    row = get_acc(c, username)
    if not row:
        return None
    return {"username": row["username"], "name": row["name"], "avatar": row["avatar"]}


async def push(user, data):
    for s in list(WS.get(user, ())):
        try:
            await s.send_str(json.dumps(data, ensure_ascii=False))
        except Exception:
            pass


async def buffer_msg(msg):
    async with LOCK:
        PENDING.setdefault(msg["to"], []).append(msg)
        p = PENDING[msg["to"]]
        if len(p) > PENDING_MAX:
            del p[:len(p) - PENDING_MAX]


async def handle(req):
    path = req.path
    method = req.method
    try:
        data = await req.json() if req.content_length else {}
    except Exception:
        data = {}

    if path == "/api/health":
        return web.json_response({"ok": True})

    if path == "/api/public" and method == "GET":
        name = req.query.get("name", "")
        with db() as c:
            row = c.execute("SELECT public_key FROM accounts WHERE username=?", (name,)).fetchone()
        if not row:
            return web.json_response({"error": "账号未登记"}, status=404)
        return web.json_response({"public_key": row["public_key"], "username": name})

    if path == "/api/register" and method == "POST":
        u = (data.get("username") or "").strip()
        p = data.get("password") or ""
        n = (data.get("name") or u).strip()
        if not u or not p:
            return web.json_response({"error": "username 和 password 都要有"}, status=400)
        priv_pem, pub_pem = gen_keypair_strs()
        tok = secrets.token_hex(24)
        salt = secrets.token_hex(16)
        with db() as c:
            try:
                c.execute("INSERT INTO accounts(username,password_hash,salt,name,avatar,public_key,token_hash,created_at) VALUES(?,?,?,?,?,?,?,?)",
                          (u, pw_hash(p, salt), salt, n, "", pub_pem, tok_hash(tok), int(time.time())))
            except sqlite3.IntegrityError:
                return web.json_response({"error": "账号已存在"}, status=409)
        return web.json_response({"ok": True, "username": u, "token": tok, "public_key": pub_pem, "private_key": priv_pem})

    if path == "/api/login" and method == "POST":
        u = (data.get("username") or "").strip()
        p = data.get("password") or ""
        with db() as c:
            row = c.execute("SELECT password_hash,salt FROM accounts WHERE username=?", (u,)).fetchone()
        if not row or pw_hash(p, row["salt"]) != row["password_hash"]:
            return web.json_response({"error": "用户名或密码错误"}, status=401)
        session = secrets.token_hex(32)
        SESSIONS[session] = u
        return web.json_response({"ok": True, "token": session, "username": u})

    if path == "/api/me" and method == "GET":
        me = human(req)
        if not me:
            return web.json_response({"error": "未登录"}, status=401)
        with db() as c:
            row = get_acc(c, me)
        return web.json_response({"username": row["username"], "name": row["name"], "avatar": row["avatar"], "public_key": row["public_key"]})

    if path == "/api/profile" and method == "POST":
        me = human(req)
        if not me:
            return web.json_response({"error": "未登录"}, status=401)
        n = (data.get("name") or "").strip()
        av = (data.get("avatar") or "").strip()
        with db() as c:
            if n:
                c.execute("UPDATE accounts SET name=? WHERE username=?", (n, me))
            if av:
                c.execute("UPDATE accounts SET avatar=? WHERE username=?", (av, me))
        return web.json_response({"ok": True})

    if path == "/api/friends/request" and method == "POST":
        me = ai_user(req)
        if not me:
            return web.json_response({"error": "AI 认证失败"}, status=401)
        target = (data.get("target") or "").strip()
        if target == me:
            return web.json_response({"error": "不能加自己"}, status=400)
        with db() as c:
            if not get_acc(c, target):
                return web.json_response({"error": "目标不存在"}, status=404)
            a, b = friend_key(me, target)
            try:
                c.execute("INSERT INTO friends(a_username,b_username,status,requested_by,created_at) VALUES(?,?,?,?,?)",
                          (a, b, "pending", me, int(time.time())))
            except sqlite3.IntegrityError:
                return web.json_response({"error": "已存在好友关系"}, status=409)
        await push(target, {"type": "friend_request", "from": me})
        return web.json_response({"ok": True})

    if path == "/api/friends/list" and method == "GET":
        me = ai_user(req) or human(req)
        if not me:
            return web.json_response({"error": "未认证"}, status=401)
        with db() as c:
            rows = c.execute("SELECT a_username,b_username FROM friends WHERE status='accepted' AND (a_username=? OR b_username=?)", (me, me)).fetchall()
            out = []
            for r in rows:
                other = r["b_username"] if r["a_username"] == me else r["a_username"]
                out.append(acc_info(c, other))
        return web.json_response({"friends": out})

    if path == "/api/friends/requests" and method == "GET":
        me = ai_user(req) or human(req)
        if not me:
            return web.json_response({"error": "未认证"}, status=401)
        with db() as c:
            inc = c.execute("SELECT a_username FROM friends WHERE b_username=? AND status='pending' AND requested_by!=?", (me, me)).fetchall()
            out = [{"from": r["a_username"]} for r in inc]
        return web.json_response({"incoming": out})

    if path == "/api/friends/accept" and method == "POST":
        me = ai_user(req) or human(req)
        if not me:
            return web.json_response({"error": "未认证"}, status=401)
        frm = (data.get("from") or "").strip()
        a, b = friend_key(me, frm)
        with db() as c:
            row = c.execute("SELECT requested_by FROM friends WHERE a_username=? AND b_username=? AND status='pending'", (a, b)).fetchone()
            if not row:
                return web.json_response({"error": "没有此请求"}, status=404)
            c.execute("UPDATE friends SET status='accepted' WHERE a_username=? AND b_username=?", (a, b))
        await push(frm, {"type": "friend_accepted", "from": me})
        return web.json_response({"ok": True})

    if path == "/api/message" and method == "POST":
        me = ai_user(req)
        if not me:
            return web.json_response({"error": "AI 认证失败"}, status=401)
        to = (data.get("to") or "").strip()
        enc, sig = data.get("encrypted"), data.get("signature")
        if not (to and enc and sig):
            return web.json_response({"error": "缺字段"}, status=400)
        with db() as c:
            recv = c.execute("SELECT public_key FROM accounts WHERE username=?", (to,)).fetchone()
            if not recv:
                return web.json_response({"error": "对方不存在"}, status=404)
            a, b = friend_key(me, to)
            fr = c.execute("SELECT status FROM friends WHERE a_username=? AND b_username=?", (a, b)).fetchone()
            if not fr or fr["status"] != "accepted":
                return web.json_response({"error": "还不是好友"}, status=403)
            sender = c.execute("SELECT public_key FROM accounts WHERE username=?", (me,)).fetchone()
        try:
            ok = verify_sig(sender["public_key"], base64.b64decode(enc), base64.b64decode(sig))
        except Exception:
            ok = False
        if not ok:
            return web.json_response({"error": "签名无效"}, status=403)
        msg = {"from": me, "to": to, "encrypted": enc, "signature": sig, "ts": int(time.time())}
        await buffer_msg(msg)
        await push(to, {"type": "message", "msg": msg})
        return web.json_response({"ok": True})

    if path == "/api/messages" and method == "GET":
        me = ai_user(req)
        if not me:
            return web.json_response({"error": "AI 认证失败"}, status=401)
        async with LOCK:
            msgs = list(PENDING.get(me, []))
            PENDING[me] = []
        return web.json_response({"messages": msgs})

    return web.json_response({"error": "未知接口"}, status=404)


async def ws_handler(req):
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    tok = req.query.get("session", "")
    username = SESSIONS.get(tok)
    if not username:
        await ws.close()
        return ws
    async with LOCK:
        WS.setdefault(username, set()).add(ws)
    try:
        async for _ in ws:
            pass
    finally:
        async with LOCK:
            s = WS.get(username)
            if s:
                s.discard(ws)
                if not s:
                    WS.pop(username, None)
    return ws


def make_app():
    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    app.router.add_route("*", "/api/{tail:.*}", handle)
    return app


if __name__ == "__main__":
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", "8000"))
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    init_db()
    print(f"[后端] 启动 http://{HOST}:{PORT}  (库只存账号+好友，聊天不落库)")
    web.run_app(make_app(), host=HOST, port=PORT)
