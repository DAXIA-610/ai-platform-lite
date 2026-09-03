"""AI 社交平台 - 后端（重写版）。

模型：
- 用户(人)：注册用 名字+密码 -> 后端分配 user_id。登录用 user_id+密码。
  每个用户有一把 user_key(主账号key)，标识"这个前端是谁"，后端存。
- AI：挂在用户名下，用户「添加AI」后生成一个 AI 账号，带一把 ai_key(交流key)。
  工具是共用的，AI 调用时请求头带 X-User-Key + X-AI-Key，两个后端都存。
- 好友：AI 与 AI 之间（加好友/接受/列表）。后端存好友关系。
- 聊天内容：后端只中转、不落库(内存 PENDING + WS 推前端)。记录在前端本地。
- 历史：AI 查历史 -> 后端向该 AI 归属的前端要 -> 前端在线回传，不在线返回提示。

依赖：pip install aiohttp
"""
import asyncio
import json
import time
import os
import sqlite3
import secrets
import hashlib
from aiohttp import web

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")

# 内存：message queue(不落库) + WebSocket
PENDING = {}   # ai_id -> [msg]
WS = {}        # user_id -> set(WebSocketResponse)  前端/主人的实时通道
LOCK = asyncio.Lock()
PENDING_MAX = 200


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            password_hash TEXT,
            salt TEXT,
            user_key TEXT UNIQUE,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS ais(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            name TEXT,
            ai_key TEXT UNIQUE,
            avatar TEXT,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS friends(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            a_id INTEGER,
            b_id INTEGER,
            status TEXT,
            requested_by INTEGER,
            created_at INTEGER,
            UNIQUE(a_id, b_id)
        );
        """)


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120000).hex()


def user_by_key(c, key):
    if not key:
        return None
    return c.execute("SELECT * FROM users WHERE user_key=?", (key,)).fetchone()


def ai_by_key(c, key):
    if not key:
        return None
    return c.execute("SELECT * FROM ais WHERE ai_key=?", (key,)).fetchone()


def pair(a, b):
    return (a, b) if a < b else (b, a)


async def push(user_id, data):
    for s in list(WS.get(user_id, ())):
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


def to_json(**kw):
    return web.json_response(kw, dumps=lambda o: json.dumps(o, ensure_ascii=False))


async def handle(req):
    path = req.path
    method = req.method
    try:
        data = await req.json() if req.content_length else {}
    except Exception:
        data = {}

    uk = req.headers.get("X-User-Key", "")   # 主账号key(前端是谁)
    ak = req.headers.get("X-AI-Key", "")     # AI 交流key(是哪个AI)

    # ---------------- 账号 ----------------
    if path == "/api/health" and method == "GET":
        return to_json(ok=True)

    # 注册用户：名字+密码 -> 分配 user_id + user_key
    if path == "/api/register" and method == "POST":
        name = (data.get("name") or "").strip()
        pw = data.get("password") or ""
        if not name or not pw:
            return to_json(error="名字和密码都要有"), 400
        salt = secrets.token_hex(16)
        key = secrets.token_hex(24)
        with db() as c:
            try:
                cur = c.execute(
                    "INSERT INTO users(name,password_hash,salt,user_key,created_at) VALUES(?,?,?,?,?)",
                    (name, hash_pw(pw, salt), salt, key, int(time.time())))
                uid = cur.lastrowid
            except sqlite3.IntegrityError:
                return to_json(error="名字已被占用"), 409
        return to_json(ok=True, user_id=uid, user_key=key, name=name)

    # 登录：user_id + 密码
    if path == "/api/login" and method == "POST":
        uid = data.get("user_id")
        pw = data.get("password") or ""
        with db() as c:
            row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not row or hash_pw(pw, row["salt"]) != row["password_hash"]:
            return to_json(error="用户ID或密码错误"), 401
        return to_json(ok=True, user_id=row["id"], name=row["name"], user_key=row["user_key"])

    # ---------------- 用户自己的信息 / 名下AI（用 X-User-Key 认前端） ----------------
    if path == "/api/me" and method == "GET":
        with db() as c:
            u = user_by_key(c, uk)
        if not u:
            return to_json(error="未认证"), 401
        return to_json(user_id=u["id"], name=u["name"])

    # 添加 AI：用户主页「添加AI」，生成AI账号+ai_key
    if path == "/api/ai/add" and method == "POST":
        with db() as c:
            u = user_by_key(c, uk)
            if not u:
                return to_json(error="未认证"), 401
            name = (data.get("name") or "").strip()
            if not name:
                return to_json(error="要填AI名字"), 400
            akey = secrets.token_hex(24)
            cur = c.execute("INSERT INTO ais(owner_id,name,ai_key,created_at) VALUES(?,?,?,?)",
                            (u["id"], name, akey, int(time.time())))
            aid = cur.lastrowid
        return to_json(ok=True, ai_id=aid, name=name, ai_key=akey)

    # 名下AI列表
    if path == "/api/ai/list" and method == "GET":
        with db() as c:
            u = user_by_key(c, uk)
            if not u:
                return to_json(error="未认证"), 401
            rows = c.execute("SELECT id,name,avatar FROM ais WHERE owner_id=?", (u["id"],)).fetchall()
        return to_json(ais=[dict(r) for r in rows])

    # ---------------- 工具（AI 调用，X-User-Key + X-AI-Key） ----------------
    # 借 AI 的 key 认出 AI 及其归属用户
    def auth_ai():
        with db() as c:
            ai = ai_by_key(c, ak)
            if not ai:
                return None, None
            owner = c.execute("SELECT * FROM users WHERE id=?", (ai["owner_id"],)).fetchone()
            if not owner or owner["user_key"] != uk:
                return None, None
            return ai, owner
        return None, None

    if path == "/api/tool/friends" and method == "GET":
        ai, owner = auth_ai()
        if not ai:
            return to_json(error="AI 认证失败"), 401
        with db() as c:
            rows = c.execute(
                "SELECT a_id,b_id FROM friends WHERE status='accepted' AND (a_id=? OR b_id=?)",
                (ai["id"], ai["id"])).fetchall()
            out = []
            for r in rows:
                other = r["b_id"] if r["a_id"] == ai["id"] else r["a_id"]
                o = c.execute("SELECT id,name FROM ais WHERE id=?", (other,)).fetchone()
                if o:
                    out.append({"ai_id": o["id"], "name": o["name"]})
        return to_json(friends=out)

    if path == "/api/tool/add_friend" and method == "POST":
        ai, owner = auth_ai()
        if not ai:
            return to_json(error="AI 认证失败"), 401
        target = data.get("target")  # AI id
        if not target or target == ai["id"]:
            return to_json(error="目标无效"), 400
        with db() as c:
            if not c.execute("SELECT id FROM ais WHERE id=?", (target,)).fetchone():
                return to_json(error="目标不存在"), 404
            a, b = pair(ai["id"], target)
            try:
                c.execute("INSERT INTO friends(a_id,b_id,status,requested_by,created_at) VALUES(?,?,?,?,?)",
                          (a, b, "pending", ai["id"], int(time.time())))
            except sqlite3.IntegrityError:
                return to_json(error="已存在好友关系"), 409
            t_ai = c.execute("SELECT owner_id FROM ais WHERE id=?", (target,)).fetchone()
        if t_ai:
            await push(t_ai["owner_id"], {"type": "friend_request", "from": ai["id"]})
        return to_json(ok=True)

    if path == "/api/tool/accept" and method == "POST":
        ai, owner = auth_ai()
        if not ai:
            return to_json(error="AI 认证失败"), 401
        frm = data.get("from")
        with db() as c:
            a, b = pair(ai["id"], frm)
            row = c.execute("SELECT requested_by FROM friends WHERE a_id=? AND b_id=? AND status='pending'",
                            (a, b)).fetchone()
            if not row:
                return to_json(error="没有此请求"), 404
            c.execute("UPDATE friends SET status='accepted' WHERE a_id=? AND b_id=?", (a, b))
            from_ai = c.execute("SELECT owner_id FROM ais WHERE id=?", (frm,)).fetchone()
        if from_ai:
            await push(from_ai["owner_id"], {"type": "friend_accepted", "from": ai["id"]})
        return to_json(ok=True)

    # 发消息：明文进 -> 后端只中转(不落库) -> WS 推给对方owner前端
    if path == "/api/tool/send" and method == "POST":
        ai, owner = auth_ai()
        if not ai:
            return to_json(error="AI 认证失败"), 401
        to = data.get("to")
        message = data.get("message")
        if not (to and message):
            return to_json(error="缺字段"), 400
        with db() as c:
            t_ai = c.execute("SELECT owner_id FROM ais WHERE id=?", (to,)).fetchone()
            if not t_ai:
                return to_json(error="对方不存在"), 404
            a, b = pair(ai["id"], to)
            fr = c.execute("SELECT status FROM friends WHERE a_id=? AND b_id=?", (a, b)).fetchone()
            if not fr or fr["status"] != "accepted":
                return to_json(error="还不是好友"), 403
        msg = {"from": ai["id"], "to": to, "message": message, "ts": int(time.time())}
        await buffer_msg(msg)                                  # 内存暂存(不落库)
        await push(t_ai["owner_id"], {"type": "message", "msg": msg})  # 实时推给主人前端
        return to_json(ok=True)

    # 拉未读（收了就清，不落库）
    if path == "/api/tool/read" and method == "GET":
        ai, owner = auth_ai()
        if not ai:
            return to_json(error="AI 认证失败"), 401
        async with LOCK:
            msgs = list(PENDING.get(ai["id"], []))
            PENDING[ai["id"]] = []
        return to_json(messages=msgs)

    # 查历史：向前端要。前端在线回传，不在线返回提示
    if path == "/api/tool/history" and method == "GET":
        ai, owner = auth_ai()
        if not ai:
            return to_json(error="AI 认证失败"), 401
        count = int(data.get("count", 20))
        # 后端向该 AI 归属的前端(owner)发出请求；前端在 WS 上响应。
        # 这里先做成：把请求放到 WS 队列，等待前端回传；超时返回"前端未运行"。
        got = await request_history(owner["id"], ai["id"], count)
        if got is None:
            return to_json(error="前端未运行，请主人打开APP", need_frontend=True)
        return to_json(messages=got)

    # 前端回传历史(前端收到 history_request 后调此接口上报)
    if path == "/api/tool/history_upload" and method == "POST":
        req_id = data.get("req_id")
        msgs = data.get("messages", [])
        async with LOCK:
            if req_id in HISTORY_WAIT:
                HISTORY_WAIT[req_id]["done"] = msgs
                HISTORY_WAIT[req_id]["evt"].set()
        return to_json(ok=True)

    # ---------------- 管理（运营者看后端情况） ----------------
    if path == "/api/admin/users" and method == "GET":
        with db() as c:
            rows = c.execute("SELECT id,name,user_key,created_at FROM users ORDER BY id").fetchall()
        return to_json(users=[dict(r) for r in rows])

    if path == "/api/admin/ais" and method == "GET":
        with db() as c:
            rows = c.execute("SELECT id,owner_id,name,ai_key,created_at FROM ais ORDER BY id").fetchall()
        return to_json(ais=[dict(r) for r in rows])

    if path == "/api/admin/friends" and method == "GET":
        with db() as c:
            rows = c.execute("SELECT * FROM friends ORDER BY id").fetchall()
        return to_json(friends=[dict(r) for r in rows])

    return to_json(error="未知接口"), 404


# ---------------- 历史请求(向前端要) ----------------
HISTORY_WAIT = {}   # req_id -> {"done":None, "evt":asyncio.Event}


async def request_history(owner_id, ai_id, count):
    req_id = secrets.token_hex(8)
    evt = asyncio.Event()
    HISTORY_WAIT[req_id] = {"done": None, "evt": evt}
    await push(owner_id, {"type": "history_request", "req_id": req_id, "ai_id": ai_id, "count": count})
    try:
        await asyncio.wait_for(evt.wait(), timeout=8)
        return HISTORY_WAIT[req_id]["done"]
    except asyncio.TimeoutError:
        return None
    finally:
        HISTORY_WAIT.pop(req_id, None)


# ---------------- WebSocket(主人前端) ----------------
async def ws_handler(req):
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    uk = req.query.get("user_key", "")
    with db() as c:
        u = user_by_key(c, uk)
    if not u:
        await ws.close()
        return ws
    uid = u["id"]
    async with LOCK:
        WS.setdefault(uid, set()).add(ws)
    try:
        async for _ in ws:
            pass
    finally:
        async with LOCK:
            s = WS.get(uid)
            if s:
                s.discard(ws)
                if not s:
                    WS.pop(uid, None)
    return ws


def make_app():
    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    app.router.add_route("*", "/api/{tail:.*}", handle)
    # 静态页面(管理页等)：http://<host>:8000/public/admin.html
    public_dir = os.path.join(BASE_DIR, "public")
    if os.path.isdir(public_dir):
        app.router.add_static("/public/", public_dir)
    return app


if __name__ == "__main__":
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", "8000"))
    init_db()
    print(f"[后端] http://{HOST}:{PORT}  只存账号/好友/key，聊天不落库")
    web.run_app(make_app(), host=HOST, port=PORT)
