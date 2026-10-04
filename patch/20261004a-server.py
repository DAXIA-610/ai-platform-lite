# -*- coding: utf-8 -*-
"""第一批·后端补丁：给 server.py 打 24 处改动。在仓库根目录跑（python3 patch/20261004a-server.py）。

规矩：任何一处匹配数 != 1 → 整体不动；写完先做语法校验，不过就不写。
"""
import ast
import sys

SRC = "server.py"

P = []


def add(desc, old, new):
    P.append((desc, old, new))


add("1 房间人数上限 8->12", r'''ROOM_MAX = 8''', r'''ROOM_MAX = 12''')

add("2 顶部 import tasks",
    r'''import sqlite3
import secrets
import hashlib
import urllib.request
import urllib.error
''',
    r'''import sqlite3
import secrets
import hashlib
import urllib.request
import urllib.error

import tasks  # 题库：抽题 / 加权 / 防重复（同目录 tasks.py）
''')

add("3 常量 AI_IDLE + ANSWER_TIMEOUT",
    r'''HISTORY_WAIT = {}
SELF = os.environ.get("PORT", "8000")''',
    r'''HISTORY_WAIT = {}
SELF = os.environ.get("PORT", "8000")
AI_IDLE = 5          # AI 该说话却一直没动静时，后端等这么久就自己推进（秒）
ANSWER_TIMEOUT = {"truth": 60, "dare": 90}   # 真人作答倒计时：真心话 60 / 大冒险 90（秒）''')

add("4 建 room_history 表 + 初始化题库表",
    r'''        # 迁移：friends 补 requested_at
        fcols = {r[1] for r in c.execute("PRAGMA table_info(friends)")}
        if "requested_at" not in fcols:
            c.execute("ALTER TABLE friends ADD COLUMN requested_at INTEGER")
''',
    r'''        # 迁移：friends 补 requested_at
        fcols = {r[1] for r in c.execute("PRAGMA table_info(friends)")}
        if "requested_at" not in fcols:
            c.execute("ALTER TABLE friends ADD COLUMN requested_at INTEGER")
        # 每局战报（写在这，读的接口留到第二批）
        c.executescript("""
        CREATE TABLE IF NOT EXISTS room_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT, game TEXT, round INTEGER,
            winner TEXT, loser TEXT, loser_choice TEXT,
            question TEXT, task_id TEXT, answer TEXT, dare TEXT,
            ts INTEGER);
        CREATE INDEX IF NOT EXISTS idx_room_history_room ON room_history(room_id);
        """)
    tasks.init_tables()
''')

add("5 房间对象加 used_task_ids",
    r'''            "created_at": time.time(), "players": [p0], "round": 0, "phase": "waiting",
            "words": None, "descs": []}''',
    r'''            "created_at": time.time(), "players": [p0], "round": 0, "phase": "waiting",
            "words": None, "descs": [], "used_task_ids": []}''')

add("6 room_status 带上题目 id / 来源",
    r'''            "winner": room.get("winner"), "loser": room.get("loser"),
            "loser_choice": room.get("loser_choice"), "question": room.get("question"),
            "answer": room.get("answer"), "dare": room.get("dare")}''',
    r'''            "winner": room.get("winner"), "loser": room.get("loser"),
            "loser_choice": room.get("loser_choice"), "question": room.get("question"),
            "task_id": room.get("task_id"), "task_source": room.get("task_source"),
            "answer": room.get("answer"), "dare": room.get("dare")}''')

add("7 新一局清掉上局题目痕迹",
    r'''    room["loser_choice"] = None; room["question"] = None; room["answer"] = None; room["dare"] = None
''',
    r'''    room["loser_choice"] = None; room["question"] = None; room["answer"] = None; room["dare"] = None
    room["task_id"] = None; room["task_source"] = None
''')

add("8 抽题 / 进question / 写战报 辅助函数",
    r'''def _truth_settle(room):''',
    r'''# ---------------- 抽题（题库在 tasks.py） ----------------
def _is_ai_key(key):
    # 玩家 key 形如 ("a", ai_id) / ("u", uid)
    return bool(key) and isinstance(key, (list, tuple)) and key[0] == "a"

def _enter_question(room):
    # 进入出题阶段：先把状态摆好，再抽一道题放进去
    room["phase"] = "question"
    room["question_started"] = time.time()
    room["question"] = None
    room["answer"] = None
    room["dare"] = None
    room["task_id"] = None
    room["task_source"] = None
    _draw_into(room)
    return room

def _draw_into(room):
    # 输家是 AI 就抽 AI 题库，是人就抽真人题库；输家选了大冒险就抽 dare
    game = "dare" if room.get("loser_choice") == "dare" else "truth"
    target = "ai" if _is_ai_key(room.get("loser")) else "human"
    used = room.setdefault("used_task_ids", [])
    t = tasks.draw_task(game, target, used)
    if not t:
        room["task_source"] = "empty"
        return None
    room["question"] = t["content"]
    room["task_id"] = t["id"]
    room["task_source"] = t["source"]
    if t["id"]:
        used.append(t["id"])
    tasks.record_use(t["id"], game, room["id"])
    return t

def _log_history(room):
    # 每局结束记一条战报
    try:
        with db() as c:
            c.execute("INSERT INTO room_history(room_id,game,round,winner,loser,loser_choice,"
                      "question,task_id,answer,dare,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (room["id"], room.get("game"), room.get("round"),
                       str(room.get("winner")), str(room.get("loser")), room.get("loser_choice"),
                       room.get("question"), room.get("task_id"), room.get("answer"),
                       room.get("dare"), int(time.time())))
    except Exception as e:
        print("[history] 写战报失败:", e)

def _truth_settle(room):''')

add("9 choose 之后立刻抽题",
    r'''    room["loser_choice"] = "dare" if choice in (1, "1", "dare", "大冒险") else "truth"
    room["phase"] = "question"
    room["question_started"] = time.time()
    room["question"] = None; room["answer"] = None; room["dare"] = None
    return "ok", room''',
    r'''    room["loser_choice"] = "dare" if choice in (1, "1", "dare", "大冒险") else "truth"
    _enter_question(room)   # 进 question 阶段的同时把题抽好
    return "ok", room''')

add("10 新增 truth_redraw / truth_use",
    r'''def truth_progress(rid):''',
    r'''def truth_redraw(rid, key):
    # 赢家在出题阶段换个题
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    if room.get("phase") != "question":
        return "bad", "现在不是出题阶段"
    if key != room.get("winner"):
        return "bad", "只有赢家能换题"
    t = _draw_into(room)
    if not t:
        return "fail", "题库抽不出题了"
    return "ok", room

def truth_use(rid, key):
    # 赢家确认就用抽到的这道题，进入回答/执行
    room = ROOMS.get(rid)
    if not room:
        return "notfound", "房间不存在"
    if room.get("phase") != "question":
        return "bad", "现在不是出题阶段"
    if key != room.get("winner"):
        return "bad", "只有赢家能定题"
    if not room.get("question"):
        return "bad", "还没有题目"
    room["phase"] = "answer"
    room["answer_started"] = time.time()
    return "ok", room

def truth_progress(rid):''')

add("11 _truth_tick 重写（AI 自动推进 + 超时兜底）",
    r'''def _truth_tick(rid):
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
        room["question_started"] = now
    elif room["phase"] == "question" and now - room.get("question_started", room.get("choices_started", now)) > 90:
        room["question"] = room.get("question") or "（赢家超时未出题，本局跳过）"
        room["phase"] = "result"
    elif room["phase"] == "answer" and now - room.get("answer_started", now) > 120:
        room["phase"] = "result"''',
    r'''def _truth_tick(rid):
    # 由 /api/game/room status 和 /api/game/play 顺带调用，所以前端正常轮询就能推动超时
    room = ROOMS.get(rid)
    if not room or room.get("game") != "truth":
        return
    now = time.time()
    ph = room.get("phase")
    if ph == "roll" and now - room.get("roll_started", now) > 60:
        for q in room["players"]:
            k = _pkey(q)
            if k not in room["rolls"]:
                room["rolls"][k] = _truth_point()
        _truth_settle(room)
    elif ph == "choose" and now - room.get("choices_started", now) > 60:
        import random
        room["loser_choice"] = random.choice(["truth", "dare"])
        _enter_question(room)
    elif ph == "question":
        started = room.get("question_started", now)
        if not room.get("question"):
            _draw_into(room)                      # 题被清空了就补一道
        if room.get("question") and _is_ai_key(room.get("winner")) and now - started > AI_IDLE:
            # 赢家是 AI：给它 AI_IDLE 秒自己出题，没动静就直接采用题库抽好的那道
            room["phase"] = "answer"
            room["answer_started"] = now
        elif now - started > 90:
            if not room.get("question"):
                room["question"] = "(赢家超时未出题，本局跳过)"
            room["phase"] = "result"
            _log_history(room)
    elif ph == "answer":
        started = room.get("answer_started", now)
        if _is_ai_key(room.get("loser")) and now - started > AI_IDLE:
            # 输家是 AI 又没自己答/执行：不编造内容，直接收局
            room["phase"] = "result"
            _log_history(room)
        elif now - started > 120:
            room["phase"] = "result"
            _log_history(room)''')

add("11b 作答超时改按 真心话60/大冒险90",
    r'''        elif now - started > 120:
            room["phase"] = "result"
            _log_history(room)''',
    r'''        elif now - started > ANSWER_TIMEOUT.get(room.get("loser_choice") or "truth", 60):
            room["phase"] = "result"
            _log_history(room)''')

add("12 /api/game/play 加 redraw / use",
    r'''                if action == "view":
                    code, res = truth_view(rid, key)''',
    r'''                if action == "redraw":
                    code, res = truth_redraw(rid, key)
                    if code != "ok":
                        return to_json(400, error=res)
                    await _broadcast_room(rid)
                    room = ROOMS.get(rid)
                    return to_json(ok=True, question=room.get("question") if room else None,
                                   task_id=room.get("task_id") if room else None)
                if action == "use":
                    code, res = truth_use(rid, key)
                    if code != "ok":
                        return to_json(400, error=res)
                    await _broadcast_room(rid)
                    return to_json(ok=True)
                if action == "view":
                    code, res = truth_view(rid, key)''')

add("13 WS 帧统一带 ts",
    r'''    data = {"type": "room_update", "room_id": rid, "room": st}''',
    r'''    data = {"type": "room_update", "room_id": rid, "ts": int(time.time()), "room": st}''')

add("14 truth 规则文本（给 AI 看的）",
    r'''    "truth": "【真心话大冒险】全员摇骰子，点数最大=赢家、最小=输家（同点随机）。输家选真心话(0)或大冒险(1)，赢家出题，输家回答/执行。\n\n流程：\n1 进房 ai_game_room('join', room_id)（游戏开始后进不去）\n2 每人摇一次 act('roll')，直接返回你的点数和你是什么身份\n3 判定后：\n   · 你赢→ progress 看输家选完没→ input 出题（大冒险就出任务）\n   · 你输→ act('choose', 0真心话|1大冒险)，工具会等你一小会；真心话→ input 回答；大冒险→ act('do', 0我已执行|1稍后执行)\n   · 都不是→ view/progress 围观\n4 本局结束，等房主开下一局\n\n⚠每个阶段只调用一次：摇过就别再摇，选过就别再选，出过题/回答过就别再输入，重复调用一定报错。每次操作后先 view 或 progress 看状态，再决定下一步，不要连着刷工具。\n超时兜底：摇骰60秒、选择60秒、出题90秒、回答120秒，超时自动跳过。",''',
    r'''    "truth": "【真心话大冒险】全员摇骰子，点数最大=赢家、最小=输家（同点随机）。输家选真心话(0)或大冒险(1)，**题目由题库自动抽**（赢家也可以自己出），输家回答/执行。\n\n流程：\n1 进房 ai_game_room('join', room_id)（游戏开始后进不去）\n2 每人摇一次 act('roll')，直接返回你的点数和你是什么身份\n3 判定后：\n   · 你赢→ 题已由题库抽好；想换→ act('redraw')；想自己出题→ input；什么都不做的话几秒后自动采用题库题\n   · 你输→ act('choose', 0真心话|1大冒险)，工具会等你一小会并把题目带回来；真心话→ input 回答；大冒险→ act('do', 0我已执行|1稍后执行)\n   · 都不是→ view/progress 围观\n4 本局结束，等房主开下一局\n\n⚠每个阶段只调用一次：摇过就别再摇，选过就别再选，出过题/回答过就别再输入，重复调用一定报错。每次操作后先 view 或 progress 看状态，再决定下一步，不要连着刷工具。\n超时兜底：摇骰60秒、选择60秒；AI 该说话时只等 5 秒，过了系统自己推进。",''')

add("15 GAME_RULES 里的超时文案",
    r'''超时兜底：摇骰60秒、选择60秒；AI 该说话时只等 5 秒，过了系统自己推进。''',
    r'''超时兜底：摇骰60秒、选择60秒、作答真心话60秒/大冒险90秒；AI 该说话时只等 5 秒，过了系统自己推进。''')

add("16 _truth_hint（给 AI 的下一步提示）",
    r'''    if ph == "question":
        if r.get("is_winner"):
            return "用 input 出题/出任务"
        return "等赢家出题，用 progress 看，别催"''',
    r'''    if ph == "question":
        if r.get("is_winner"):
            return "题库已自动抽好题；想换 act('redraw')、想自己出 input，都不做的话几秒后自动采用"
        return "等赢家定题，用 progress 看，别催"''')

add("17 MCP 新工具 ai_game_custom_task",
    r'''# ---------------- app ----------------''',
    r'''@mcp.tool()
def ai_game_custom_task(content: str, game: str = "dare", target: str = "ai", tags: str = "") -> str:
    """往题库加一条自定义任务（所有房间共享）。game: dare=大冒险 / truth=真心话；target: ai=只发给AI / human=只发给真人；tags 逗号分隔。"""
    tag_list = [x.strip() for x in tags.split(",") if x.strip()] or None
    task, err = tasks.custom_add(content, game=game, target=target, tags=tag_list)
    if err:
        return "失败：" + err
    return "已加入题库 %s（%s / 给%s）" % (task["id"], task["game"], "AI" if task["target"] == "ai" else "真人")


# ---------------- app ----------------''')

add("18 只读的题库统计接口",
    r'''    # ---- admin ----''',
    r'''    # ---- 题库（只读，方便核对抽题）----
    if path == "/api/game/tasks" and method == "GET":
        game = request.query_params.get("game") or "truth"
        return to_json(ok=True, **tasks.stats(game))

    # ---- admin ----''')

add("19 赢家自己出题要标 manual",
    r'''    room["question"] = t[:500]
    room["phase"] = "answer"; room["answer_started"] = time.time()
    return "ok", room''',
    r'''    room["question"] = t[:500]
    room["task_source"] = "manual"      # 赢家自己出的题，跟题库抽的区分开
    room["task_id"] = None
    room["phase"] = "answer"; room["answer_started"] = time.time()
    return "ok", room''')

add("20 正常作答也要写战报",
    r'''    room["answer"] = t[:500]
    room["phase"] = "result"
    return "ok", room''',
    r'''    room["answer"] = t[:500]
    room["phase"] = "result"
    _log_history(room)
    return "ok", room''')

add("21 大冒险选完也要写战报",
    r'''    room["dare"] = "done" if val in (0, "0") else "later"  # 我已执行=0, 稍后执行=1
    room["phase"] = "result"
    return "ok", room''',
    r'''    room["dare"] = "done" if val in (0, "0") else "later"  # 我已执行=0, 稍后执行=1
    room["phase"] = "result"
    _log_history(room)
    return "ok", room''')

add("22 投票不再占着全局房间锁死等 60 秒",
    r'''                await _broadcast_room(rid)
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
                return to_json(ok=True, **res)''',
    r'''                await _broadcast_room(rid)
                # 不在这里等其他人投票：以前会占着全局房间锁死等 60 秒，把别的房间一起卡住。
                # 现在投出最后一票的瞬间就结算，前端轮询 status 即可看到。
                return to_json(ok=True, **res)''')


def main():
    src = open(SRC, encoding="utf-8").read()
    out = src
    bad = []
    for desc, old, new in P:
        n = out.count(old)
        if n != 1:
            bad.append((desc, n))
            continue
        out = out.replace(old, new, 1)
    if bad:
        print("!! 匹配数不对，整体不动:")
        for d, n in bad:
            print("   -", d, "出现", n, "次")
        return 1
    try:
        ast.parse(out)
    except SyntaxError as e:
        print("!! 改完语法不过，整体不动:", e)
        return 1
    open(SRC, "w", encoding="utf-8").write(out)
    print("OK server.py 改了 %d 处，语法校验通过" % len(P))
    return 0


sys.exit(main())
