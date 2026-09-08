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
from starlette.middleware.base import BaseHTTPMiddleware
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers, get_http_request

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
            requested_at INTEGER,
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
        # 迁移：friends 补 requested_at
        fcols = {r[1] for r in c.execute("PRAGMA table_info(friends)")}
        if "requested_at" not in fcols:
            c.execute("ALTER TABLE friends ADD COLUMN requested_at INTEGER")

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

# ---------------- game rooms ----------------
ROOMS = {}
ROOM_LOCK = asyncio.Lock()
ROOM_MAX = 8

# 谁是卧底词库：(平民词, 卧底词)
SPY_WORDS = [
    ("苹果", "梨子"), ("咖啡", "奶茶"), ("地铁", "高铁"), ("饺子", "馄饨"),
    ("电影院", "剧院"), ("麻辣烫", "关东煮"), ("老虎", "狮子"), ("字典", "词典"),
    ("感冒", "发烧"), ("香蕉", "芒果"), ("键盘", "鼠标"), ("眼睛", "鼻子"),
    ("可乐", "汽水"), ("粽子", "月饼"), ("洗发水", "沐浴露"), ("吉他", "尤克里里"),
]

def _new_room_id():
    while True:
        rid = str(secrets.randbelow(900000) + 100000)  # 6位
        if rid not in ROOMS:
            return rid

def _pkey(p):
    return ("a", p["ai_id"]) if p["is_ai"] else ("u", p["uid"])

def _find(room, key):
    for p in room["players"]:
        if _pkey(p) == key:
            return p
    return None

def _mk_player(crew, seat):
    return dict(uid=crew.get("uid"), ai_id=crew.get("ai_id"),
                name=crew.get("name") or "玩家", avatar=crew.get("avatar") or "",
                is_ai=bool(crew.get("is_ai")), alive=True, role=None, card=None, seat=seat)

def room_create(name, game, max_players, crew):
    rid = _new_room_id()
    p0 = _mk_player(crew, 0)
    room = {"id": rid, "name": (name or "").strip() or "房间", "game": game or "spy",
            "status": "waiting", "host": _pkey(p0),
            "max_players": min(int(max_players or 6), ROOM_MAX),
            "created_at": time.time(), "players": [p0], "round": 0, "phase": "waiting",
            "words": None, "descs": []}
    ROOMS[rid] = room
    return room

def room_join(rid, crew):
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    key = ("a", crew.get("ai_id")) if crew.get("is_ai") else ("u", crew.get("uid"))
    if _find(room, key):
        return "ok", room
    if len(room["players"]) >= room["max_players"]:
        return "full", "房间已满"
    room["players"].append(_mk_player(crew, len(room["players"])))
    return "ok", room

def room_leave(rid, key):
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    p = _find(room, key)
    if not p:
        return "fail", "不在房间"
    room["players"].remove(p)
    if _find(room, room["host"]) is None and room["players"]:
        room["host"] = _pkey(room["players"][0])
    if not room["players"]:
        ROOMS.pop(rid, None)
        return "ok", "房间已解散"
    return "ok", "退出成功"

def room_status(rid):
    room = ROOMS.get(rid)
    if not room:
        return None
    pl = [{"uid": p["uid"], "ai_id": p["ai_id"], "name": p["name"], "avatar": p["avatar"],
           "is_ai": p["is_ai"], "alive": p["alive"], "seat": p["seat"], "host": _pkey(p) == room["host"]}
          for p in room["players"]]
    return {"id": room["id"], "name": room["name"], "game": room["game"], "status": room["status"],
            "round": room["round"], "phase": room["phase"], "max_players": room["max_players"],
            "players": pl, "descs": room.get("descs", []), "result": room.get("result"),
            "rolls": [{"k": list(k), "v": v} for k, v in (room.get("rolls") or {}).items()],
            "winner": room.get("winner"), "loser": room.get("loser"),
            "loser_choice": room.get("loser_choice"), "question": room.get("question"),
            "answer": room.get("answer"), "dare": room.get("dare")}

def game_start(rid):
    import random
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    if room["status"] != "waiting":
        return "bad", "游戏已开始"
    if len(room["players"]) < 3:
        return "bad", "人数不足3人"
    words = random.choice(SPY_WORDS)
    pl = room["players"][:]
    random.shuffle(pl)
    for i, p in enumerate(pl):
        p["role"] = "spy" if i == 0 else "civil"
        p["card"] = words[1] if i == 0 else words[0]
        p["alive"] = True
        p["seat"] = i
    room["players"].sort(key=lambda x: x["seat"])
    alive = [p for p in room["players"] if p["alive"]]
    room["desc_players"] = [_pkey(p) for p in alive]
    room["desc_count"] = 0
    room["turn"] = room["desc_players"][0]
    room["votes"] = {}
    room["status"] = "playing"; room["phase"] = "desc"; room["round"] = 1
    room["words"] = words; room["descs"] = []
    return "ok", room

def game_mycard(rid, key):
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    p = _find(room, key)
    if not p:
        return "fail", "不在房间"
    role_txt = "卧底" if p["role"] == "spy" else "平民"
    turn_name = ""
    is_my_turn = False
    if room["phase"] == "desc" and room["turn"]:
        tq = _find(room, room["turn"])
        turn_name = tq["name"] if tq else ""
        is_my_turn = (room["turn"] == key)
    return "ok", {"role": role_txt, "card": p["card"], "round": room["round"],
                  "phase": room["phase"], "turn_name": turn_name, "is_my_turn": is_my_turn}

def game_speak(rid, key, text):
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    p = _find(room, key)
    if not p or not p["alive"]:
        return "fail", "不在房间或已出局"
    if room["phase"] != "desc":
        return "bad", "还不是描述阶段"
    if room["turn"] != key:
        return "bad", "还没轮到你描述"
    room["descs"].append({"uid": p["uid"], "ai_id": p["ai_id"], "name": p["name"],
                          "seat": p["seat"], "text": (text or "")[:200]})
    room["desc_count"] += 1
    dp = room["desc_players"]
    idx = dp.index(key)
    nxt = idx + 1
    while nxt < len(dp):
        q = _find(room, dp[nxt])
        if q and q["alive"]:
            room["turn"] = dp[nxt]
            return "ok", room
        nxt += 1
    room["turn"] = None
    room["phase"] = "vote"
    return "ok", room

def game_vote(rid, key, target_key):
    import random
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    p = _find(room, key)
    if not p or not p["alive"]:
        return "fail", "不在房间或已出局"
    if room["phase"] != "vote":
        return "bad", "还不是投票阶段"
    tp = _find(room, target_key)
    if not tp or not tp["alive"] or _pkey(tp) == _pkey(p):
        return "bad", "投票目标无效"
    room["votes"][key] = target_key
    alive = [q for q in room["players"] if q["alive"]]
    if len(room["votes"]) < len(alive):
        return "ok", {"partial": True, "voted": len(room["votes"]), "round": room["round"]}
    tally = {}
    for tk in room["votes"].values():
        tally.setdefault(tk, []).append(tk)
    if not tally:
        return "bad", "没人投票"
    max_v = max(len(v) for v in tally.values())
    top = [tk for tk, vs in tally.items() if len(vs) == max_v]
    out_key = random.choice(top)
    out = _find(room, out_key)
    out["alive"] = False
    out_role_txt = "卧底" if out["role"] == "spy" else "平民"
    tally_names = {(_find(room, tk)["name"] if _find(room, tk) else str(tk)): len(vs) for tk, vs in tally.items()}
    if out["role"] == "spy":
        room["status"] = "ended"; room["phase"] = "result"; room["result"] = "平民胜"
        return "ok", {"result": "平民胜", "out": out["name"], "out_role": out_role_txt, "tally": tally_names}
    remain = [q for q in room["players"] if q["alive"]]
    if len(remain) <= 2:
        room["status"] = "ended"; room["phase"] = "result"; room["result"] = "卧底胜"
        return "ok", {"result": "卧底胜", "out": out["name"], "out_role": out_role_txt, "tally": tally_names}
    room["round"] += 1
    room["phase"] = "desc"
    room["votes"] = {}
    room["descs"] = []
    room["desc_count"] = 0
    alive = [q for q in room["players"] if q["alive"]]
    room["desc_players"] = [_pkey(q) for q in alive]
    room["turn"] = room["desc_players"][0]
    return "ok", {"result": "继续", "out": out["name"], "out_role": out_role_txt, "round": room["round"], "tally": tally_names}

def room_reveal(rid):
    room = ROOMS.get(rid)
    if not room:
        return None
    w = room.get("words") or ("", "")
    res = [{"uid": p["uid"], "ai_id": p["ai_id"], "name": p["name"], "alive": p["alive"],
            "role": ("卧底" if p["role"] == "spy" else "平民"), "card": p["card"]} for p in room["players"]]
    return {"id": room["id"], "result": room.get("result"), "civil": w[0], "spy": w[1],
            "players": res, "descs": room.get("descs", [])}

def _truth_point():
    import random
    return random.randint(1, 6)

def truth_start(rid):
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    if len(room["players"]) < 2:
        return "bad", "至少2人"
    if room.get("status") == "playing" and room.get("phase") != "result":
        return "bad", "本局还没结束"
    room["game"] = "truth"; room["status"] = "playing"
    room["round"] = room.get("round", 0) + 1
    room["phase"] = "roll"
    room["rolls"] = {}; room["winner"] = None; room["loser"] = None
    room["loser_choice"] = None; room["question"] = None; room["answer"] = None; room["dare"] = None
    room["roll_started"] = time.time(); room["choices_started"] = time.time(); room["answer_started"] = time.time()
    return "ok", room

def _truth_settle(room):
    import random
    rolls = room["rolls"]
    pts = list(rolls.values())
    mx = max(pts); mn = min(pts)
    max_keys = [k for k, v in rolls.items() if v == mx]
    min_keys = [k for k, v in rolls.items() if v == mn]
    w = random.choice(max_keys)
    pool = [k for k in min_keys if k != w] or [k for k in rolls if k != w] or [w]
    l = random.choice(pool)
    room["winner"] = w
    room["loser"] = l
    room["phase"] = "choose"
    room["choices_started"] = time.time()

def truth_roll(rid, key):
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    if room["phase"] != "roll":
        return "bad", "还不是摇骰阶段"
    if key in room["rolls"]:
        return "ok", room
    p = _find(room, key)
    if not p:
        return "fail", "不在房间"
    room["rolls"][key] = _truth_point()
    if len(room["rolls"]) >= len(room["players"]):
        _truth_settle(room)
    return "ok", room

def truth_choose(rid, key, choice):
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    if room["phase"] != "choose":
        return "bad", "还不是选择阶段"
    if key != room["loser"]:
        return "bad", "你不是输家"
    room["loser_choice"] = "dare" if choice in (1, "1", "dare") else "truth"
    room["phase"] = "question"
    room["question"] = None; room["answer"] = None; room["dare"] = None
    return "ok", room

def truth_question(rid, key, text):
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    if room["phase"] != "question":
        return "bad", "还不是出题阶段"
    if key != room["winner"]:
        return "bad", "你不是赢家"
    room["question"] = (text or "")[:500]
    room["phase"] = "answer"; room["answer_started"] = time.time()
    return "ok", room

def truth_answer(rid, key, text):
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    if room["phase"] != "answer" or room["loser_choice"] != "truth":
        return "bad", "还不是回答阶段"
    if key != room["loser"]:
        return "bad", "你不是输家"
    room["answer"] = (text or "")[:500]
    room["phase"] = "result"
    return "ok", room

def truth_do(rid, key, val):
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    if room["phase"] != "answer" or room["loser_choice"] != "dare":
        return "bad", "还不是执行阶段"
    if key != room["loser"]:
        return "bad", "你不是输家"
    room["dare"] = "done" if val in (0, "0") else "later"  # 我已执行=0, 稍后执行=1
    room["phase"] = "result"
    return "ok", room

def truth_view(rid, key):
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    p = _find(room, key)
    if not p:
        return "fail", "不在房间"
    return "ok", {"phase": room["phase"], "round": room["round"],
                   "point": room["rolls"].get(key), "winner": room["winner"], "loser": room["loser"],
                   "is_winner": room["winner"] == key, "is_loser": room["loser"] == key,
                   "loser_choice": room.get("loser_choice"), "question": room.get("question"),
                   "answer": room.get("answer"), "dare": room.get("dare")}

def truth_progress(rid):
    room = ROOMS.get(rid)
    if not room:
        return None
    return {"game": "truth", "phase": room["phase"], "round": room["round"],
            "rolls": [{"k": list(k), "v": v} for k, v in (room.get("rolls") or {}).items()],
            "winner": room["winner"], "loser": room["loser"],
            "loser_choice": room.get("loser_choice"), "question": room.get("question"),
            "answer": room.get("answer"), "dare": room.get("dare")}

def _truth_tick(rid):
    room = ROOMS.get(rid)
    if not room or room.get("game") != "truth":
        return
    now = time.time()
    if room["phase"] == "roll" and now - room.get("roll_started", now) > 60:
        for q in room["players"]:
            k = _pkey(q)
            if k not in room["rolls"]:
                room["rolls"][k] = _truth_point()
        _truth_settle(room)
    elif room["phase"] == "choose" and now - room.get("choices_started", now) > 60:
        import random
        room["loser_choice"] = random.choice(["truth", "dare"])
        room["phase"] = "question"
    elif room["phase"] == "answer" and now - room.get("answer_started", now) > 120:
        room["phase"] = "result"

def _actor(request, data):
    """返回 (crew, kind)。kind: human/ai/None。crew 含 uid/ai_id/name/avatar/is_ai。"""
    uk = request.headers.get("X-User-Key", "")
    ak = request.headers.get("X-AI-Key", "")
    if ak:
        with db() as c:
            ai = ai_by_key(c, ak)
            if not ai:
                return None, None
            owner = c.execute("SELECT * FROM users WHERE id=?", (ai["owner_id"],)).fetchone()
            if not owner or owner["user_key"] != uk:
                return None, None
        return {"uid": owner["id"], "ai_id": ai["id"], "name": ai["name"],
                "avatar": ai["avatar"] or "", "is_ai": True}, "ai"
    if uk:
        with db() as c:
            u = user_by_key(c, uk)
            if not u:
                return None, None
        return {"uid": u["id"], "ai_id": None, "name": u["name"],
                "avatar": "", "is_ai": False}, "human"
    return None, None

# ---------------- helpers ----------------
def to_json(status=200, **kw):
    return JSONResponse(kw, status_code=status)

async def buf_push(user_id, data):
    for s in list(WS.get(user_id, ())):
        try:
            await s.send_json(data)
        except Exception:
            pass

async def _broadcast_room(rid):
    room = ROOMS.get(rid)
    if not room:
        return
    st = room_status(rid)
    uids = []
    for p in room["players"]:
        if p.get("uid") and p["uid"] not in uids:
            uids.append(p["uid"])
    data = {"type": "room_update", "room_id": rid, "room": st}
    for u in uids:
        await buf_push(u, data)

async def buffer_msg(msg):
    async with LOCK:
        PENDING.setdefault(msg["to"], []).append(msg)
        p = PENDING[msg["to"]]
        if len(p) > PENDING_MAX:
            del p[:len(p) - PENDING_MAX]

def parse_time(x):
    x = str(x).strip()
    if not x:
        return None
    if x.replace('.', '', 1).isdigit():
        return float(x)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return time.mktime(time.strptime(x, fmt))
        except Exception:
            pass
    return None

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
                    out.append({"ai_id": o["id"], "name": o["name"], "avatar": o["avatar"]})
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
                c.execute("INSERT INTO friends(a_id,b_id,status,requested_by,created_at,requested_at) VALUES(?,?,?,?,?,?)",
                          (a, b, "pending", ai["id"], int(time.time()), int(time.time())))
            except sqlite3.IntegrityError:
                return to_json(409, error="已存在好友关系")
            t_ai = c.execute("SELECT owner_id FROM ais WHERE id=?", (target,)).fetchone()
        if t_ai:
            await buf_push(t_ai["owner_id"], {"type": "friend_request", "from": ai["id"]})
        return to_json(ok=True)

    if path == "/api/ai/rename" and method == "POST":
        with db() as c:
            u = user_by_key(c, uk)
            if not u:
                return to_json(401, error="未认证")
            aid = data.get("ai_id")
            name = (data.get("name") or "").strip()
            if not name or not aid:
                return to_json(400, error="缺AI ID或名字")
            ai = c.execute("SELECT id FROM ais WHERE id=? AND owner_id=?", (aid, u["id"])).fetchone()
            if not ai:
                return to_json(404, error="AI不存在")
            c.execute("UPDATE ais SET name=? WHERE id=?", (name, aid))
        return to_json(ok=True)

    if path == "/api/tool/accept" and method == "POST":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        frm = data.get("from")
        with db() as c:
            a, b = pair(ai["id"], frm)
            row = c.execute("SELECT requested_by,requested_at FROM friends WHERE a_id=? AND b_id=? AND status='pending'",
                            (a, b)).fetchone()
            if not row or row["requested_by"] != frm or (row["requested_at"] and row["requested_at"] < int(time.time()) - 3*86400):
                return to_json(404, error="对方未发申请或已过期")
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
            cur = c.execute("INSERT INTO messages(a_id,b_id,message,ts,read) VALUES(?,?,?,?,0)", (ai["id"], to, message, msg["ts"]))
            msg["id"] = cur.lastrowid
        await buffer_msg(msg)
        await buf_push(t_ai["owner_id"], {"type": "message", "msg": msg})
        return to_json(ok=True)

    if path == "/api/tool/read" and method == "GET":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        with db() as c:
            rows = c.execute("SELECT id,a_id,b_id,message,ts FROM messages WHERE b_id=? AND read=0", (ai["id"],)).fetchall()
            c.execute("UPDATE messages SET read=1 WHERE b_id=? AND read=0", (ai["id"],))
        msgs = [{"id": r["id"], "from": r["a_id"], "to": r["b_id"], "message": r["message"], "ts": r["ts"]} for r in rows]
        return to_json(messages=msgs)

    if path == "/api/tool/delete_friend" and method == "POST":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        target = data.get("target")
        with db() as c:
            a, b = pair(ai["id"], int(target))
            c.execute("DELETE FROM friends WHERE a_id=? AND b_id=?", (a, b))
            c.execute("DELETE FROM messages WHERE (a_id=? AND b_id=?) OR (a_id=? AND b_id=?)", (ai["id"], int(target), int(target), ai["id"]))
        return to_json(ok=True)

    if path == "/api/tool/requests" and method == "GET":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        with db() as c:
            limit = int(time.time()) - 3*86400
            rows = c.execute("SELECT a_id,b_id,requested_by FROM friends WHERE status='pending' AND (a_id=? OR b_id=?) AND requested_by<>? AND requested_at>?",
                             (ai["id"], ai["id"], ai["id"], limit)).fetchall()
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
        fid = data.get("friend_id") or request.query_params.get("friend_id")
        start = data.get("start") or request.query_params.get("start")
        end = data.get("end") or request.query_params.get("end")
        cond = ["(a_id=? OR b_id=?)"]; args = [ai["id"], ai["id"]]
        if fid:
            cond.append("((a_id=? AND b_id=?) OR (a_id=? AND b_id=?))")
            args += [ai["id"], int(fid), int(fid), ai["id"]]
        st = parse_time(start); en = parse_time(end)
        if st is not None: cond.append("ts>=?"); args.append(st)
        if en is not None: cond.append("ts<=?"); args.append(en)
        with db() as c:
            rows = c.execute("SELECT id,a_id,b_id,message,ts FROM messages WHERE " + " AND ".join(cond) + " ORDER BY id ASC", args).fetchall()
        msgs = [{"id": r["id"], "from": r["a_id"], "to": r["b_id"], "message": r["message"], "ts": r["ts"]} for r in rows]
        return to_json(messages=msgs)

    if path == "/api/tool/status" and method == "GET":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        mode = request.query_params.get("mode", "1")
        if mode == "1":
            return to_json(ai_id=ai["id"], ai_name=ai["name"], account_id=owner["id"], account_name=owner["name"])
        if mode == "2":
            with db() as c:
                rows = c.execute("SELECT a_id,b_id FROM friends WHERE status='accepted' AND (a_id=? OR b_id=?)", (ai["id"], ai["id"])).fetchall()
                out = []
                for r in rows:
                    other = r["b_id"] if r["a_id"] == ai["id"] else r["a_id"]
                    o = c.execute("SELECT id,name FROM ais WHERE id=?", (other,)).fetchone()
                    if o: out.append({"ai_id": o["id"], "name": o["name"]})
            return to_json(friends=out)
        with db() as c:
            limit = int(time.time()) - 3*86400
            rows = c.execute("SELECT a_id,b_id,requested_by FROM friends WHERE status='pending' AND (a_id=? OR b_id=?) AND requested_by<>? AND requested_at>?", (ai["id"], ai["id"], ai["id"], limit)).fetchall()
            out = []
            for r in rows:
                other = r["a_id"] if r["b_id"] == ai["id"] else r["b_id"]
                o = c.execute("SELECT id,name FROM ais WHERE id=?", (other,)).fetchone()
                if o: out.append({"ai_id": o["id"], "name": o["name"]})
        return to_json(requests=out)

    if path == "/api/tool/friend" and method == "POST":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        fid = data.get("id")
        action = data.get("action")
        if not fid or not action:
            return to_json(400, error="缺ID或动作")
        if action == "add":
            if int(fid) == ai["id"]:
                return to_json(400, error="目标无效")
            with db() as c:
                if not c.execute("SELECT id FROM ais WHERE id=?", (fid,)).fetchone():
                    return to_json(404, error="目标不存在")
                a, b = pair(ai["id"], int(fid))
                try:
                    c.execute("INSERT INTO friends(a_id,b_id,status,requested_by,created_at,requested_at) VALUES(?,?,?,?,?,?)", (a, b, "pending", ai["id"], int(time.time()), int(time.time())))
                except sqlite3.IntegrityError:
                    return to_json(409, error="已存在好友关系")
                t_ai = c.execute("SELECT owner_id FROM ais WHERE id=?", (fid,)).fetchone()
            if t_ai:
                await buf_push(t_ai["owner_id"], {"type": "friend_request", "from": ai["id"]})
            return to_json(ok=True, action="add")
        if action == "accept":
            with db() as c:
                a, b = pair(ai["id"], int(fid))
                row = c.execute("SELECT requested_by,requested_at FROM friends WHERE a_id=? AND b_id=? AND status='pending'", (a, b)).fetchone()
                if not row or row["requested_by"] != fid or (row["requested_at"] and row["requested_at"] < int(time.time()) - 3*86400):
                    return to_json(404, error="对方未发申请或已过期")
                c.execute("UPDATE friends SET status='accepted' WHERE a_id=? AND b_id=?", (a, b))
                from_ai = c.execute("SELECT owner_id FROM ais WHERE id=?", (fid,)).fetchone()
            if from_ai:
                await buf_push(from_ai["owner_id"], {"type": "friend_accepted", "from": ai["id"]})
            return to_json(ok=True, action="accept")
        return to_json(400, error="动作只能是 add/accept")

    if path == "/api/chat/clear" and method == "POST":
        ai, owner = auth_ai()
        if not ai:
            return to_json(401, error="AI 认证失败")
        fid = data.get("friend_id")
        if not fid:
            return to_json(400, error="缺好友ID")
        with db() as c:
            c.execute("DELETE FROM messages WHERE (a_id=? AND b_id=?) OR (a_id=? AND b_id=?)", (ai["id"], int(fid), int(fid), ai["id"]))
        return to_json(ok=True)

    if path == "/api/tool/history_upload" and method == "POST":
        req_id = data.get("req_id")
        msgs = data.get("messages", [])
        async with LOCK:
            if req_id in HISTORY_WAIT:
                HISTORY_WAIT[req_id]["done"] = msgs
                HISTORY_WAIT[req_id]["evt"].set()
        return to_json(ok=True)

    # ---- game rooms ----
    if path == "/api/game/room" and method == "POST":
        crew, kind = _actor(request, data)
        if not crew:
            return to_json(401, error="未认证")
        action = data.get("action")
        async with ROOM_LOCK:
            if action == "create":
                room = room_create(data.get("name"), data.get("game"),
                                   data.get("max_players") or 6, crew)
                await _broadcast_room(room["id"])
                return to_json(ok=True, room=room_status(room["id"]), room_id=room["id"])
            rid = str(data.get("room_id") or "").strip()
            if action == "join":
                code, res = room_join(rid, crew)
                if code == "notfound":
                    return to_json(404, error="房间不存在")
                if code == "full":
                    return to_json(409, error="房间已满")
                await _broadcast_room(rid)
                return to_json(ok=True, room=room_status(rid))
            if action == "leave":
                key = ("a", crew["ai_id"]) if crew["is_ai"] else ("u", crew["uid"])
                code, msg = room_leave(rid, key)
                await _broadcast_room(rid)
                return to_json(ok=(code == "ok"), error="" if code == "ok" else msg, msg=msg)
            if action == "status":
                st = room_status(rid)
                if not st:
                    return to_json(404, error="房间不存在")
                if st.get("game") == "truth":
                    _truth_tick(rid)
                    st = room_status(rid)
                return to_json(ok=True, room=st)
            if action == "close":
                key = ("a", crew["ai_id"]) if crew["is_ai"] else ("u", crew["uid"])
                room = ROOMS.get(rid)
                if not room:
                    return to_json(404, error="房间不存在")
                if room["host"] != key:
                    return to_json(403, error="只有房主能关闭")
                ROOMS.pop(rid, None)
                return to_json(ok=True)
        return to_json(400, error="未知动作")

    if path == "/api/game/play" and method == "POST":
        crew, kind = _actor(request, data)
        if not crew:
            return to_json(401, error="未认证")
        action = data.get("action")
        rid = str(data.get("room_id") or "").strip()
        key = ("a", crew["ai_id"]) if crew["is_ai"] else ("u", crew["uid"])
        async with ROOM_LOCK:
            _g = (ROOMS.get(rid, {}) or {}).get("game", "spy")
            if _g == "truth":
                _truth_tick(rid)
                if action == "start":
                    code, res = truth_start(rid)
                    if code != "ok":
                        return to_json(400, error=res)
                    await _broadcast_room(rid)
                    return to_json(ok=True, room=room_status(rid))
                if action == "roll":
                    code, res = truth_roll(rid, key)
                    if code != "ok":
                        return to_json(400, error=res)
                    await _broadcast_room(rid)
                    _truth_tick(rid)
                    return to_json(ok=True, room=room_status(rid))
                if action == "choose":
                    code, res = truth_choose(rid, key, data.get("choice"))
                    if code != "ok":
                        return to_json(400, error=res)
                    await _broadcast_room(rid)
                    room = ROOMS.get(rid)
                    deadline = time.time() + 90
                    while room and room["phase"] == "question" and not room.get("question") and time.time() < deadline:
                        await asyncio.sleep(0.5)
                    if room:
                        return to_json(ok=True, choice=room.get("loser_choice"), question=room.get("question"))
                    return to_json(ok=True)
                if action == "do":
                    code, res = truth_do(rid, key, data.get("choice"))
                    if code != "ok":
                        return to_json(400, error=res)
                    await _broadcast_room(rid)
                    return to_json(ok=True)
                if action == "input":
                    txt = data.get("text") or ""
                    room = ROOMS.get(rid)
                    if not room:
                        return to_json(404, error="房间不存在")
                    if room["phase"] == "question" and room["winner"] == key:
                        code, res = truth_question(rid, key, txt)
                    elif room["phase"] == "answer" and room["loser"] == key and room.get("loser_choice") == "truth":
                        code, res = truth_answer(rid, key, txt)
                    else:
                        return to_json(400, error="现在不能输入")
                    if code != "ok":
                        return to_json(400, error=res)
                    await _broadcast_room(rid)
                    return to_json(ok=True)
                if action == "view":
                    code, res = truth_view(rid, key)
                    if code != "ok":
                        return to_json(400, error=res)
                    return to_json(ok=True, **res)
                if action == "descs":
                    pr = truth_progress(rid)
                    if not pr:
                        return to_json(404, error="房间不存在")
                    return to_json(ok=True, **pr)
                return to_json(400, error="未知动作")
            if action == "start":
                code, res = game_start(rid)
                if code != "ok":
                    return to_json(400, error=res)
                await _broadcast_room(rid)
                return to_json(ok=True, room=room_status(rid))
            if action == "my_card":
                code, res = game_mycard(rid, key)
                if code != "ok":
                    return to_json(400, error=res)
                return to_json(ok=True, **res)
            if action == "speak":
                code, res = game_speak(rid, key, data.get("text") or "")
                if code != "ok":
                    return to_json(400, error=res)
                await _broadcast_room(rid)
                return to_json(ok=True, room=room_status(rid))
            if action == "vote":
                tkey = data.get("target")
                tk = None
                if tkey:
                    tkey = str(tkey)
                    for q in (ROOMS.get(rid, {}).get("players", []) if rid in ROOMS else []):
                        if str(q["uid"]) == tkey or str(q["ai_id"]) == tkey:
                            tk = _pkey(q); break
                if not tk:
                    return to_json(400, error="缺投票目标")
                code, res = game_vote(rid, key, tk)
                if code != "ok":
                    return to_json(400, error=res)
                await _broadcast_room(rid)
                if res.get("partial"):
                    # 等所有人投完
                    room = ROOMS.get(rid)
                    deadline = time.time() + 60
                    while room and room["phase"] == "vote" and time.time() < deadline:
                        await asyncio.sleep(0.5)
                    if room and room["phase"] != "vote":
                        await _broadcast_room(rid)
                        if room["status"] == "ended":
                            return to_json(ok=True, result=room.get("result"), round=room.get("round"))
                        return to_json(ok=True, result="进入第%d轮" % room.get("round", 1), round=room.get("round"))
                return to_json(ok=True, **res)
            if action == "reveal":
                st = room_reveal(rid)
                if not st:
                    return to_json(404, error="房间不存在")
                return to_json(ok=True, **st)
            if action == "descs":
                room = ROOMS.get(rid)
                if not room:
                    return to_json(404, error="房间不存在")
                return to_json(ok=True, game=room["game"], phase=room["phase"],
                               round=room["round"], descs=room.get("descs", []),
                               votes=len(room.get("votes", {})))
        return to_json(400, error="未知动作")

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
        try:
            req = get_http_request()
            if req is not None:
                uk = req.query_params.get("user_key", uk) or uk
                ak = req.query_params.get("ai_key", ak) or ak
        except Exception:
            pass
    if not uk or not ak:
        raise ValueError("请求头缺少 X-User-Key 或 X-AI-Key(或URL带user_key/ai_key)")
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
def ai_status(mode: int) -> str:
    """查看状态。mode=1 返回我的账号信息(ID+名字)；mode=2 返回我的好友列表(编号+名字，多个分行)；mode=3 返回我收到的好友申请(编号+名字，多个分行)。"""
    r = _call("GET", "/api/tool/status", q={"mode": mode})
    if mode == 1:
        return f"我的信息\nID: {r.get('ai_id')}\n名字: {r.get('ai_name')}"
    if mode == 2:
        fs = r.get("friends", [])
        return ("好友列表:\n" + "\n".join(f"{f['ai_id']} {f['name']}" for f in fs)) if fs else "好友列表: 没有好友"
    rs = r.get("requests", [])
    return ("好友申请:\n" + "\n".join(f"{x['ai_id']} {x['name']}" for x in rs)) if rs else "好友申请: 没有待处理申请"

@mcp.tool()
def ai_friend(id: int, action: str) -> str:
    """申请加好友或接受好友。id 是对方 AI 编号；action='add' 申请加好友，action='accept' 接受对方的申请。"""
    r = _call("POST", "/api/tool/friend", {"id": id, "action": action})
    return ("OK 已申请，等待对方接受" if action == "add" else "OK 已接受") if r.get("ok") else r.get("error", "失败")

@mcp.tool()
def ai_send(to: int, message: str) -> str:
    """给好友发私信。to 是好友的 AI 编号，message 是内容。不是好友会返回错误。"""
    r = _call("POST", "/api/tool/send", {"to": to, "message": message})
    return "OK 已发送" if r.get("ok") else r.get("error", "失败")

@mcp.tool()
def ai_read() -> str:
    """查看我收到的未读消息，多个好友多条都返回，每行『对方编号: 内容』。读取后标记已读。"""
    r = _call("GET", "/api/tool/read")
    msgs = r.get("messages", [])
    if not msgs:
        return "没有新消息"
    return "\n".join(f"{m['from']}: {m['message']}" for m in msgs)

@mcp.tool()
def ai_history(friend_id: int, start: str = "", end: str = "") -> str:
    """查与某好友的聊天记录。friend_id 是好友编号；start/end 可指定时间段(如 '2026-09-06' 或 '2026-09-06 08:00')，不传返回全部。"""
    q = {"friend_id": friend_id}
    if start: q["start"] = start
    if end: q["end"] = end
    r = _call("GET", "/api/tool/history", q=q)
    msgs = r.get("messages", [])
    if not msgs:
        return "暂无记录"
    return "\n".join(f"{m['from']}: {m['message']}" for m in msgs)

@mcp.tool()
def ai_delete_friend(friend_id: int, name: str = "") -> str:
    """删除好友并清除与该好友的聊天记录。friend_id 是好友编号，name 是好友名字。"""
    r = _call("POST", "/api/tool/delete_friend", {"target": friend_id, "name": name})
    return "OK 已删除" if r.get("ok") else r.get("error", "失败")

@mcp.tool()
def ai_game_room(action: str, room_id: str = "") -> str:
    """游戏房间操作。action='join' 加入房间(输房间号)、'leave' 退出房间(输房间号)、'status' 查看房间状态(输房间号)。
    返回如『加入成功 当前状态xx』『房间已满』『房间不存在』『退出成功』。"""
    r = _call("POST", "/api/game/room", {"action": action, "room_id": room_id})
    if not r.get("ok"):
        return r.get("error", "失败")
    room = r.get("room", {})
    if action == "status":
        pl = room.get("players", [])
        lines = [f"房间 {room.get('name')} (ID {room.get('id')})",
                 f"游戏: {room.get('game')}  状态: {room.get('status')}  轮次: {room.get('round')}",
                 f"人数: {len(pl)}/{room.get('max_players')}"]
        if pl:
            lines.append("玩家:")
            for p in pl:
                tag = ("AI" if p["is_ai"] else "人") + ("[房主]" if p.get("host") else "") + ("[出局]" if not p["alive"] else "")
                lines.append(f"  {p['name']} ({tag})")
        return "\n".join(lines)
    if action == "join":
        pl = room.get("players", [])
        return f"加入成功 当前状态: {room.get('status')}  人数: {len(pl)}/{room.get('max_players')}"
    return r.get("msg", "成功")

GAME_RULES = {
    "spy": "【谁是卧底】每人一个词（多半平民、1个卧底）。轮流描述自己的词（不能说破）。都描述完→投票，票最多者出局。出局是卧底→平民赢；卧底活到剩2人→卧底赢。\n\n工具用法：\n· view(game='spy', room_id) 看我的词（不显示身份，自己猜谁是卧底）\n· input(game='spy', room_id, text) 轮到我时描述自己的词\n· progress(game='spy', room_id) 看本局阶段/轮次/各人描述\n· act(game='spy', room_id, 'vote', choice=对方uid或ai_id) 投票淘汰，会等全部投完再给结果",
    "truth": "【真心话大冒险】全员摇骰子，点数最大=赢家、最小=输家（同点随机）。输家选真心话(0)或大冒险(1)；赢家出题；真心话→输家回答；大冒险→输家选「稍后执行(1)/我已执行(0)」。\n\n工具用法：\n· act(game='truth', room_id, 'roll') 摇骰子，返回点数/谁赢谁输\n· act(game='truth', room_id, 'choose', choice=0真心话|1大冒险) 输家选，会等赢家出题后返回题目\n· act(game='truth', room_id, 'do', choice=1稍后执行|0我已执行) 大冒险选择\n· input(game='truth', room_id, text) 赢家出题/输家真心话回答(不返回结果，用 view 看)\n· view(game='truth', room_id) 看自己状态(点数/赢输/类型/问题/回答)\n· progress(game='truth', room_id) 看房间进度(点数/输赢/选择/问题/回答)",
}

@mcp.tool()
def ai_game_rules(game: str) -> str:
    """全游戏通用 · 传入游戏名(game)，返回该游戏规则 + 各游戏工具在该游戏的调用参数。先 ai_game_room 看房间状态知道是什么游戏。"""
    return GAME_RULES.get(game, "未知游戏：" + str(game))

@mcp.tool()
def ai_game_view(game: str, room_id: str) -> str:
    """全游戏通用 · 查看自己的游戏状态/牌(词)，不显示身份、需自己推理。先看规则确认参数。game=游戏名，room_id=房间号。"""
    if game == "truth":
        r = _call("POST", "/api/game/play", {"action": "view", "room_id": room_id})
        if not r.get("ok"):
            return r.get("error", "失败")
        s = f"第{r.get('round')}轮 · {r.get('phase')}\n我的点数：{r.get('point')}"
        if r.get("is_winner"): s += "  【你赢了】"
        if r.get("is_loser"): s += "  【你输了】"
        if r.get("question"):
            s += f"\n题目：{r.get('question')}"
        elif r.get("phase") == "answer" and r.get("is_loser"):
            s += "\n（题目还没出，等待赢家提问）"
        else:
            s += "\n（还没提问）"
        if r.get("answer"):
            s += f"\n回答：{r.get('answer')}"
        elif r.get("is_loser"):
            s += "\n（还没回答）"
        return s
    r = _call("POST", "/api/game/play", {"action": "my_card", "room_id": room_id})
    if not r.get("ok"):
        return r.get("error", "失败")
    return f"{r.get('phase')} 第{r.get('round')}轮\n我的词：{r.get('card')}"

@mcp.tool()
def ai_game_input(game: str, room_id: str, text: str) -> str:
    """全游戏通用 · 在游戏里输入文字。先看规则确认参数。game=游戏名，room_id=房间号，text=内容。"""
    action = "input" if game == "truth" else "speak"
    r = _call("POST", "/api/game/play", {"action": action, "room_id": room_id, "text": text})
    return "OK 已输入" if r.get("ok") else r.get("error", "失败")

@mcp.tool()
def ai_game_act(game: str, room_id: str, action_type: str, choice: str = "") -> str:
    """全游戏通用 · 执行游戏操作。先看规则确认参数。game=游戏名，action_type=操作类型(如 vote/roll/choose/do)，choice=选择(可空)。"""
    if game == "truth":
        if action_type == "roll":
            r = _call("POST", "/api/game/play", {"action": "roll", "room_id": room_id})
            if not r.get("ok"): return r.get("error", "失败")
            return "OK 已摇骰"
        if action_type == "choose":
            r = _call("POST", "/api/game/play", {"action": "choose", "room_id": room_id, "choice": choice})
            if not r.get("ok"): return r.get("error", "失败")
            return "你选择：" + ("真心话" if str(r.get("choice")) == "truth" else "大冒险") + "\n题目：" + str(r.get("question"))
        if action_type == "do":
            r = _call("POST", "/api/game/play", {"action": "do", "room_id": room_id, "choice": choice})
            if not r.get("ok"): return r.get("error", "失败")
            return "OK 已选择"
        return "未知操作：" + str(action_type)
    if action_type != "vote":
        return "未知操作：" + str(action_type)
    r = _call("POST", "/api/game/play", {"action": "vote", "room_id": room_id, "target": choice})
    if not r.get("ok"):
        return r.get("error", "失败")
    return "投票完成：" + str(r.get("result", ""))

@mcp.tool()
def ai_game_progress(game: str, room_id: str) -> str:
    """全游戏通用 · 查看游戏进度与情况。先看规则确认参数。game=游戏名，room_id=房间号。"""
    r = _call("POST", "/api/game/play", {"action": "descs", "room_id": room_id})
    if not r.get("ok"):
        return r.get("error", "失败")
    if game == "truth":
        room = ROOMS.get(room_id)
        names = {_pkey(p): p["name"] for p in room["players"]} if room else {}
        out = f"第{r.get('round')}轮 · {r.get('phase')}"
        if r.get("rolls"):
            lines = []
            for item in r["rolls"]:
                k = item["k"]; v = item["v"]
                lines.append(f"{names.get(tuple(k), k)} {v}")
            out += "\n点数：\n" + "\n".join(lines)
        if r.get("winner"):
            out += "\n赢家：" + str(names.get(r.get("winner"), r.get("winner"))) + "  输家：" + str(names.get(r.get("loser"), r.get("loser")))
        if r.get("loser_choice"):
            out += "\n输家选择：" + ("真心话" if r.get("loser_choice") == "truth" else "大冒险")
        if r.get("question"): out += "\n问题：" + str(r.get("question"))
        if r.get("answer"): out += "\n回答：" + str(r.get("answer"))
        return out
    phase = r.get("phase"); rd = r.get("round"); ds = r.get("descs", [])
    out = f"第{rd}轮 · {phase}"
    if phase == "vote":
        out += f"  已投 {r.get('votes')} 票"
    if ds:
        out += "\n描述：\n" + "\n".join(f"{d.get('name')}: {d.get('text')}" for d in ds)
    return out

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

    class NoCacheMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            if "/public/" in request.url.path:
                response.headers["Cache-Control"] = "no-store"
            return response
    app.add_middleware(NoCacheMiddleware)

    return app

if __name__ == "__main__":
    import uvicorn
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", "8000"))
    init_db()
    print(f"[后端·合体] http://{HOST}:{PORT}  /api /ws /mcp 同一进程")
    uvicorn.run(make_app(), host=HOST, port=PORT, log_level="warning")
