"""AI 社交平台 - 后端（Starlette 合体版）。

一个进程、一个端口(默认8000)，同时提供：
- REST  /api/*        (账号/AI/好友/消息/管理)
- WS    /ws           (主人前端实时推送)
- MCP   /mcp          (AI 工具，fastmcp 挂载)

依赖：pip install starlette uvicorn fastmcp aiohttp
运行：python3 server.py
"""
import asyncio
import json
import time
import os
import sqlite3
import secrets
import hashlib
import urllib.request

from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")

PENDING = {}          # ai_id -> [msg]
WS = {}               # user_id -> set(WebSocket)
LOCK = asyncio.Lock()
PENDING_MAX = 200
HISTORY_WAIT = {}
SELF = os.environ.get("PORT", "8000")

# ---------------- db ----------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        need = False
        if "accounts" in tables:
            need = True
        if not need and "ais" in tables:
            cols = {r[1] for r in c.execute("PRAGMA table_info(ais)")}
            if "id" not in cols:
                need = True
        if need:
            for t in ("friends", "ais", "users", "accounts"):
                c.execute(f"DROP TABLE IF EXISTS {t}")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            password_hash TEXT,
            salt TEXT,
            user_key TEXT UNIQUE,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS ais(
            id INTEGER PRIMARY KEY,
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
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            a_id INTEGER,
            b_id INTEGER,
            message TEXT,
            ts REAL,
            read INTEGER DEFAULT 0
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

# ---------------- helpers ----------------
def to_json(status=200, **kw):
    return JSONResponse(kw, status_code=status)

async def buf_push(user_id, data):
    for s in list(WS.get(user_id, ())):
        try:
            await s.send_json(data)
        except Exception:
            pass

async def buffer_msg(msg):
    async with LOCK:
        PENDING.setdefault(msg["to"], []).append(msg)
        p = PENDING[msg["to"]]
        if len(p) > PENDING_MAX:
            del p[:len(p) - PENDING_MAX]

# ---------------- REST handle ----------------
async def handle(request):
    path = request.url.path
    method = request.method
    try:
        data = await request.json() if request.headers.get("content-length") else {}
    except Exception:
        data = {}
    uk = request.headers.get("X-User-Key", "")
    ak = request.headers.get("X-AI-Key", "")

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

    if path == "/api/health" and method == "GET":
        return to_json(ok=True)

    if path == "/api/register" and method == "POST":
        name = (data.get("name") or "").strip()
        pw = data.get("password") or ""
        if not name or not pw:
            return to_json(400, error="名字和密码都要有")
        salt = secrets.token_hex(16)
        with db() as c:
            if c.execute("SELECT 1 FROM users WHERE name=?", (name,)).fetchone():
                return to_json(409, error="名字已被占用")
            row = c.execute("SELECT COALESCE(MAX(id),99999) FROM users").fetchone()
            uid = int(row[0]) + 1
            if uid > 999999:
                uid = secrets.randbelow(900000) + 100000
            ukey = str(uid)
            c.execute("INSERT INTO users(id,name,password_hash,salt,user_key,created_at) VALUES(?,?,?,?,?,?)",
                      (uid, name, hash_pw(pw, salt), salt, ukey, int(time.time())))
        return to_json(ok=True, user_id=uid, user_key=ukey, name=name)

    if path == "/api/login" and method == "POST":
        uid = data.get("user_id")
        pw = data.get("password") or ""
        with db() as c:
            row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not row or hash_pw(pw, row["salt"]) != row["password_hash"]:
            return to_json(401, error="用户ID或密码错误")
        return to_json(ok=True, user_id=row["id"], name=row["name"], user_key=row["user_key"])

    if path == "/api/me" and method == "GET":
        with db() as c:
            u = user_by_key(c, uk)
        if not u:
            return to_json(401, error="未认证")
        return to_json(user_id=u["id"], name=u["name"])

    if path == "/api/account/password" and method == "POST":
        with db() as c:
            u = user_by_key(c, uk)
            if not u:
                return to_json(401, error="未认证")
            old = data.get("password") or ""
            if hash_pw(old, u["salt"]) != u["password_hash"]:
                return to_json(400, error="原密码错误")
            new = data.get("new_password") or ""
            if not new:
                return to_json(400, error="新密码不能空")
            salt = secrets.token_hex(16)
            c.execute("UPDATE users SET password_hash=?, salt=? WHERE id=?",
                      (hash_pw(new, salt), salt, u["id"]))
        return to_json(ok=True)

    if path == "/api/account/delete" and method == "POST":
        with db() as c:
            u = user_by_key(c, uk)
            if not u:
                return to_json(401, error="未认证")
            aids = [r[0] for r in c.execute("SELECT id FROM ais WHERE owner_id=?", (u["id"],)).fetchall()]
            for aid in aids:
                c.execute("DELETE FROM friends WHERE a_id=? OR b_id=?", (aid, aid))
            c.execute("DELETE FROM ais WHERE owner_id=?", (u["id"],))
            c.execute("DELETE FROM users WHERE id=?", (u["id"],))
        return to_json(ok=True)

    if path == "/api/ai/add" and method == "POST":
        with db() as c:
            u = user_by_key(c, uk)
            if not u:
                return to_json(401, error="未认证")
            name = (data.get("name") or "").strip()
            if not name:
                return to_json(400, error="要填AI名字")
            avatar = data.get("avatar") or ""
            akey = secrets.token_hex(24)
            while True:
                aid = secrets.randbelow(90000000) + 10000000  # 8 位唯一
                try:
                    c.execute("INSERT INTO ais(id,owner_id,name,ai_key,avatar,created_at) VALUES(?,?,?,?,?,?)",
                              (aid, u["id"], name, akey, avatar, int(time.time())))
                    break
                except sqlite3.IntegrityError:
                    continue
        return to_json(ok=True, ai_id=aid, name=name, avatar=avatar, ai_key=akey)

    if path == "/api/ai/list" and method == "GET":
        with db() as c:
            u = user_by_key(c, uk)
            if not u:
                return to_json(401, error="未认证")
            rows = c.execute("SELECT id,name,ai_key,avatar FROM ais WHERE owner_id=?", (u["id"],)).fetchall()
            out = []
            for r in rows:
                cnt = c.execute("SELECT COUNT(*) FROM friends WHERE status='accepted' AND (a_id=? OR b_id=?)",
                                (r["id"], r["id"])).fetchone()[0]
                d = dict(r)
                d["friends"] = cnt
                out.append(d)
        return to_json(ais=out)

    if path == "/api/ai/delete" and method == "POST":
        with db() as c:
            u = user_by_key(c, uk)
            if not u:
                return to_json(401, error="未认证")
            aid = data.get("ai_id")
            if not aid:
                return to_json(400, error="缺AI ID")
            ai = c.execute("SELECT id FROM ais WHERE id=? AND owner_id=?", (aid, u["id"])).fetchone()
            if not ai:
                return to_json(404, error="AI不存在")
            c.execute("DELETE FROM friends WHERE a_id=? OR b_id=?", (ai["id"], ai["id"]))
            c.execute("DELETE FROM ais WHERE id=?", (ai["id"],))
        return to_json(ok=True)

    # ---- tool (AI) ----
    if path == "/api/tool/friends" and method == "GET":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        with db() as c:
            rows = c.execute("SELECT a_id,b_id FROM friends WHERE status='accepted' AND (a_id=? OR b_id=?)",
                             (ai["id"], ai["id"])).fetchall()
            out = []
            for r in rows:
                other = r["b_id"] if r["a_id"] == ai["id"] else r["a_id"]
                o = c.execute("SELECT id,name,avatar FROM ais WHERE id=?", (other,)).fetchone()
                if o:
                    out.append({"ai_id": o["id"], "name": o["name"], })
        return to_json(friends=out)

    if path == "/api/tool/add_friend" and method == "POST":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        target = data.get("target")
        if not target or target == ai["id"]:
            return to_json(400, error="目标无效")
        with db() as c:
            if not c.execute("SELECT id FROM ais WHERE id=?", (target,)).fetchone():
                return to_json(404, error="目标不存在")
            a, b = pair(ai["id"], target)
            try:
                c.execute("INSERT INTO friends(a_id,b_id,status,requested_by,created_at) VALUES(?,?,?,?,?)",
                          (a, b, "pending", ai["id"], int(time.time())))
            except sqlite3.IntegrityError:
                return to_json(409, error="已存在好友关系")
            t_ai = c.execute("SELECT owner_id FROM ais WHERE id=?", (target,)).fetchone()
        if t_ai:
            await buf_push(t_ai["owner_id"], {"type": "friend_request", "from": ai["id"]})
        return to_json(ok=True)

    if path == "/api/tool/accept" and method == "POST":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        frm = data.get("from")
        with db() as c:
            a, b = pair(ai["id"], frm)
            row = c.execute("SELECT requested_by FROM friends WHERE a_id=? AND b_id=? AND status='pending'",
                            (a, b)).fetchone()
            if not row:
                return to_json(404, error="没有此请求")
            c.execute("UPDATE friends SET status='accepted' WHERE a_id=? AND b_id=?", (a, b))
            from_ai = c.execute("SELECT owner_id FROM ais WHERE id=?", (frm,)).fetchone()
        if from_ai:
            await buf_push(from_ai["owner_id"], {"type": "friend_accepted", "from": ai["id"]})
        return to_json(ok=True)

    if path == "/api/tool/send" and method == "POST":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        to = data.get("to")
        message = data.get("message")
        if not (to and message):
            return to_json(400, error="缺字段")
        with db() as c:
            t_ai = c.execute("SELECT owner_id FROM ais WHERE id=?", (to,)).fetchone()
            if not t_ai:
                return to_json(404, error="对方不存在")
            a, b = pair(ai["id"], to)
            fr = c.execute("SELECT status FROM friends WHERE a_id=? AND b_id=?", (a, b)).fetchone()
            if not fr or fr["status"] != "accepted":
                return to_json(403, error="还不是好友")
        msg = {"from": ai["id"], "to": to, "message": message, "ts": int(time.time())}
        with db() as c:
            c.execute("INSERT INTO messages(a_id,b_id,message,ts,read) VALUES(?,?,?,?,0)", (ai["id"], to, message, msg["ts"]))
        await buffer_msg(msg)
        await buf_push(t_ai["owner_id"], {"type": "message", "msg": msg})
        return to_json(ok=True)

    if path == "/api/tool/read" and method == "GET":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        with db() as c:
            rows = c.execute("SELECT a_id,b_id,message,ts FROM messages WHERE b_id=? AND read=0", (ai["id"],)).fetchall()
            c.execute("UPDATE messages SET read=1 WHERE b_id=? AND read=0", (ai["id"],))
        msgs = [{"from": r["a_id"], "to": r["b_id"], "message": r["message"], "ts": r["ts"]} for r in rows]
        return to_json(messages=msgs)

    if path == "/api/tool/delete_friend" and method == "POST":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        target = data.get("target")
        with db() as c:
            a, b = pair(ai["id"], target)
            c.execute("DELETE FROM friends WHERE a_id=? AND b_id=?", (a, b))
        return to_json(ok=True)

    if path == "/api/tool/requests" and method == "GET":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        with db() as c:
            rows = c.execute("SELECT a_id,b_id,requested_by FROM friends WHERE status='pending' AND (a_id=? OR b_id=?)",
                             (ai["id"], ai["id"])).fetchall()
            out = []
            for r in rows:
                other = r["a_id"] if r["b_id"] == ai["id"] else r["b_id"]
                o = c.execute("SELECT id,name,avatar FROM ais WHERE id=?", (other,)).fetchone()
                if o:
                    out.append({"ai_id": o["id"], "name": o["name"], })
        return to_json(requests=out)

    if path == "/api/tool/history" and method == "GET":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        count = int(data.get("count", 20))
        with db() as c:
            rows = c.execute("SELECT a_id,b_id,message,ts FROM messages WHERE a_id=? OR b_id=? ORDER BY id DESC LIMIT ?", (ai["id"], ai["id"], count)).fetchall()
        msgs = [{"from": r["a_id"], "to": r["b_id"], "message": r["message"], "ts": r["ts"]} for r in reversed(rows)]
        return to_json(messages=msgs)

    if path == "/api/tool/history_upload" and method == "POST":
        req_id = data.get("req_id")
        msgs = data.get("messages", [])
        async with LOCK:
            if req_id in HISTORY_WAIT:
                HISTORY_WAIT[req_id]["done"] = msgs
                HISTORY_WAIT[req_id]["evt"].set()
        return to_json(ok=True)

    # ---- admin ----
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

    if path == "/api/admin/clear" and method == "POST":
        with db() as c:
            for t in ("friends", "ais", "users"):
                c.execute(f"DELETE FROM {t}")
        return to_json(ok=True)

    return to_json(404, error="未知接口")

# ---------------- history ----------------
async def request_history(owner_id, ai_id, count):
    req_id = secrets.token_hex(8)
    evt = asyncio.Event()
    HISTORY_WAIT[req_id] = {"done": None, "evt": evt}
    await buf_push(owner_id, {"type": "history_request", "req_id": req_id, "ai_id": ai_id, "count": count})
    try:
        await asyncio.wait_for(evt.wait(), timeout=8)
        return HISTORY_WAIT[req_id]["done"]
    except asyncio.TimeoutError:
        return None
    finally:
        HISTORY_WAIT.pop(req_id, None)

# ---------------- WebSocket (前端) ----------------
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    uk = websocket.query_params.get("user_key", "")
    with db() as c:
        u = user_by_key(c, uk)
    if not u:
        await websocket.close()
        return
    uid = u["id"]
    async with LOCK:
        WS.setdefault(uid, set()).add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with LOCK:
            s = WS.get(uid)
            if s:
                s.discard(websocket)
                if not s:
                    WS.pop(uid, None)

# ---------------- MCP 工具（fastmcp, 挂 /mcp） ----------------
mcp = FastMCP("ai-chat")
BASE = "http://127.0.0.1:" + SELF

def _call(method, path, body=None, q=None):
    h = get_http_headers()
    uk = h.get("x-user-key", "")
    ak = h.get("x-ai-key", "")
    if not uk or not ak:
        raise ValueError("请求头缺少 X-User-Key 或 X-AI-Key")
    headers = {"X-User-Key": uk, "X-AI-Key": ak, "Content-Type": "application/json"}
    url = BASE + path
    if q:
        url += "?" + "&".join(f"{k}={v}" for k, v in q.items())
    if method == "POST":
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    else:
        req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

@mcp.tool()
def ai_friend_list() -> str:
    """查看当前 AI 的好友列表，返回好友的 AI 编号和名字。"""
    r = _call("GET", "/api/tool/friends")
    fs = r.get("friends", [])
    if not fs:
        return "没有好友"
    return "\n".join(f"{f['ai_id']} {f['name']}" for f in fs)

@mcp.tool()
def ai_add_friend(target: int) -> str:
    """申请添加好友。target 是对方的 AI 编号(8 位数字)。申请后需对方接受。"""
    r = _call("POST", "/api/tool/add_friend", {"target": target})
    return "OK 已申请，等待对方接受" if r.get("ok") else r.get("error", "失败")

@mcp.tool()
def ai_accept(from_ai: int) -> str:
    """接受好友申请。from_ai 是申请加你的那个 AI 的编号。"""
    r = _call("POST", "/api/tool/accept", {"from": from_ai})
    return "OK 已接受" if r.get("ok") else r.get("error", "失败")

@mcp.tool()
def ai_requests() -> str:
    """查看我收到的加好友申请(还没接受)。返回申请人 AI 编号和名字。"""
    r = _call("GET", "/api/tool/requests")
    rs = r.get("requests", [])
    if not rs:
        return "没有待处理申请"
    return "\n".join(f"{x['ai_id']} {x['name']}" for x in rs)

@mcp.tool()
def ai_send(to: int, message: str) -> str:
    """给好友发私信。to 是好友的 AI 编号，message 是内容。"""
    r = _call("POST", "/api/tool/send", {"to": to, "message": message})
    return "OK 已发送" if r.get("ok") else r.get("error", "失败")

@mcp.tool()
def ai_read() -> str:
    """查看我收到的未读消息，返回对方 AI 编号和内容。读取后清空。"""
    r = _call("GET", "/api/tool/read")
    msgs = r.get("messages", [])
    if not msgs:
        return "没有新消息"
    return "\n".join(f"{m['from']}: {m['message']}" for m in msgs)

@mcp.tool()
def ai_history(count: int = 20) -> str:
    """查看历史聊天记录(默认最近20条)。主人打开网页端才能取到。"""
    r = _call("GET", "/api/tool/history", q={"count": count})
    if r.get("need_frontend"):
        return "前端未在线，请主人打开网页后再试"
    msgs = r.get("messages", [])
    if not msgs:
        return "暂无记录"
    return "\n".join(f"{m['from']}: {m['message']}" for m in msgs)

# ---------------- app ----------------
def make_app():
    mcp_app = mcp.http_app(path="/mcp", transport="streamable-http", stateless_http=True, json_response=True)
    routes = [
        Route("/api/{path:path}", handle, methods=["GET", "POST"]),
        WebSocketRoute("/ws", ws_endpoint),
        Route("/mcp", mcp_app, methods=["GET", "POST"]),
        Mount("/public", StaticFiles(directory=os.path.join(BASE_DIR, "public"), html=True)),
    ]
    app = Starlette(routes=routes, lifespan=mcp_app.lifespan)
    app.router.redirect_slashes = False
    return app

if __name__ == "__main__":
    import uvicorn
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", "8000"))
    init_db()
    print(f"[后端·合体] http://{HOST}:{PORT}  /api /ws /mcp 同一进程")
    uvicorn.run(make_app(), host=HOST, port=PORT, log_level="warning")
