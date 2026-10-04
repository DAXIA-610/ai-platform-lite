"""题库：抽题（按 target 筛 / weight 加权 / 防重复）。

内置题库（只读）：
    data/truth.json   真心话
    data/dare.json    大冒险
自定义题库（可写，MCP 工具 ai_game_custom_task 往里加）：
    data/custom_tasks.json

防重复分三层：
    1. 房间级 room["used_task_ids"]      —— 同一房间里抽过的绝不再抽
    2. 全局最近 RECENT_N 次使用          —— 跨房间也不容易撞题
    3. 上面两层都排空时，退回第 1 层放宽 —— 保证一定能抽到
题库文件有 10 秒缓存，改完不用重启后端。
"""
import json
import os
import random
import sqlite3
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(BASE_DIR, "data.db")

GAME_FILES = {"truth": ["truth.json"], "dare": ["dare.json"]}
CUSTOM_FILE = "custom_tasks.json"
CACHE_TTL = 10.0
RECENT_N = 30

_cache = {}
_cache_ts = {}


# ---------------- 基础 ----------------
def _db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_tables():
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS task_usage(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT, game TEXT, room_id TEXT, ts INTEGER);
        CREATE INDEX IF NOT EXISTS idx_task_usage_id ON task_usage(id);
        """)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        print("[tasks] 题库读不了:", path, e)
        return None
    return d if isinstance(d, dict) else None


def _norm(t, source):
    """把题库里的一条整理成内部格式；坏的丢掉。"""
    if not isinstance(t, dict):
        return None
    content = str(t.get("content") or "").strip()
    if not content:
        return None
    return {
        "id": str(t.get("id") or "").strip(),
        "content": content,
        "target": str(t.get("target") or "human").strip(),
        "tags": t.get("tags") or [],
        "weight": float(t.get("weight") or 1) or 1.0,
        "rating": t.get("rating"),
        "source": source,
    }


def load_tasks(game):
    """某游戏的全部题目（内置 + 自定义）。"""
    now = time.time()
    if game in _cache and now - _cache_ts.get(game, 0) < CACHE_TTL:
        return _cache[game]
    out = []
    for fn in GAME_FILES.get(game, []):
        d = _read_json(os.path.join(DATA_DIR, fn))
        if d:
            for t in (d.get("tasks") or []):
                n = _norm(t, "builtin")
                if n:
                    out.append(n)
    d = _read_json(os.path.join(DATA_DIR, CUSTOM_FILE))
    if d:
        for t in (d.get("tasks") or []):
            if (t.get("game") or game) != game:
                continue
            n = _norm(t, "custom")
            if n:
                out.append(n)
    _cache[game] = out
    _cache_ts[game] = now
    return out


def recent_used_ids(n=RECENT_N):
    try:
        with _db() as c:
            rows = c.execute("SELECT task_id FROM task_usage ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return {r["task_id"] for r in rows if r["task_id"]}
    except Exception as e:
        print("[tasks] 读使用记录失败:", e)
        return set()


def record_use(task_id, game, room_id):
    if not task_id:
        return
    try:
        with _db() as c:
            c.execute("INSERT INTO task_usage(task_id,game,room_id,ts) VALUES(?,?,?,?)",
                      (task_id, game, room_id, int(time.time())))
    except Exception as e:
        print("[tasks] 写使用记录失败:", e)


def draw_task(game, target, used_ids=None, avoid_recent=True):
    """抽一题。target: human / ai。抽不到返回 None。"""
    used_ids = {str(x) for x in (used_ids or [])}
    pool = [t for t in load_tasks(game) if t["target"] == target]
    if not pool:
        pool = load_tasks(game)                      # 该 target 没题 → 退回全量
    if not pool:
        return None
    cand = [t for t in pool if t["id"] not in used_ids]
    if not cand:
        cand = list(pool)                            # 房间内全抽过了 → 放宽第 1 层
    if avoid_recent:
        recent = recent_used_ids()
        c2 = [t for t in cand if t["id"] not in recent]
        if c2:
            cand = c2
    weights = [max(0.01, t["weight"]) for t in cand]
    return random.choices(cand, weights=weights, k=1)[0]


def custom_add(content, game="dare", target="ai", tags=None, weight=5):
    """往自定义题库加一条（所有房间共享）。返回 (task, err)。"""
    content = (content or "").strip()
    if not content:
        return None, "内容不能为空"
    if game not in ("truth", "dare"):
        return None, "game 只能是 truth 或 dare"
    if target not in ("ai", "human"):
        return None, "target 只能是 ai 或 human"
    path = os.path.join(DATA_DIR, CUSTOM_FILE)
    d = _read_json(path) or {"version": 1, "tasks": []}
    lst = d.setdefault("tasks", [])
    ids = {str(t.get("id")) for t in lst}
    n = 1
    while ("c%04d" % n) in ids:
        n += 1
    task = {
        "id": "c%04d" % n, "content": content, "game": game, "target": target,
        "tags": tags or [target, "custom"], "weight": weight,
        "rating": None, "source": "custom",
    }
    lst.append(task)
    d["version"] = d.get("version", 1)
    d["updated_at"] = time.strftime("%Y-%m-%d")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    _cache.pop(game, None)
    _cache_ts.pop(game, None)
    return task, None


def stats(game):
    ts = load_tasks(game)
    return {
        "game": game, "total": len(ts),
        "human": sum(1 for t in ts if t["target"] == "human"),
        "ai": sum(1 for t in ts if t["target"] == "ai"),
        "custom": sum(1 for t in ts if t["source"] == "custom"),
    }
