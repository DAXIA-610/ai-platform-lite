# -*- coding: utf-8 -*-
"""第一批·文档补丁：更新 README.md 和 开发者交接说明.md。在仓库根目录跑。"""
import sys

P = {}


def add(path, desc, old, new):
    P.setdefault(path, []).append((desc, old, new))


README = "README.md"

add(README, "目录结构",
    r'''server.py                     后端（API + WS + MCP 一体）
mcp_server.py                 MCP 工具定义（供 AI 用）
public/app.html               网页版前端
public/admin.html             管理页
app/                          Flutter APP（app/lib/*.dart）''',
    r'''server.py                     后端（API + WS + MCP 一体，含游戏状态机）
tasks.py                      题库：抽题 / 按 weight 加权 / 防重复
data/truth.json               真心话题库（target=human / ai）
data/dare.json                大冒险题库
data/custom_tasks.json        自定义题库（运行时生成，MCP 工具往里加）
mcp_server.py                 MCP 工具定义（独立进程版，可不用）
public/app.html               网页版前端
public/admin.html             管理页
app/                          Flutter APP（app/lib/*.dart）''')

add(README, "truth 状态机 + 抽题规则",
    r'''### 真心话大冒险 `truth`
```
waiting → roll（全员摇骰，1 分钟自动）
        → choose（输家选：0 真心话 / 1 大冒险，1 分钟没选自动随机）
        → question（赢家出题）
        → answer（真心话：答题，2 分钟超时；大冒险：选 1 稍后执行 / 0 我已执行）
        → result（房主可开下一局）
赢家 = 点数最大、输家 = 点数最小（同点随机，且保证赢家 ≠ 输家）
```

**AI 玩真心话大冒险的完整调用链**
1. `ai_game_room(action='join', room_id)` 进房
2. `act('roll')` 摇骰
3. 判定后：
   - 赢了 → `progress` 看输家选啥 → `input` 出题
   - 输了 → `act('choose', 0真心话|1大冒险)`（会等题目返回）；真心话 → `input` 回答；大冒险 → `act('do', 1稍后|0已执行)`
   - 旁观 → `view` 看输家选择 / 题目 / 回答''',
    r'''### 真心话大冒险 `truth`
```
waiting → roll（全员摇骰，1 分钟自动）
        → choose（输家选：0 真心话 / 1 大冒险，1 分钟没选自动随机）
        → question（进这个阶段的同时，后端就按输家的类型把题抽好了）
        → answer（真心话：60 秒；大冒险：90 秒）
        → result（房主可开下一局）
赢家 = 点数最大、输家 = 点数最小（同点随机，且保证赢家 ≠ 输家）
```

**抽题规则**（`tasks.py` + `data/*.json`）
- 按**输家**类型选题库：输家是真人 → `target=human` 的题；输家是 AI → `target=ai` 的题。
- 按输家选的内容选文件：真心话 → `data/truth.json`；大冒险 → `data/dare.json`。
- `weight` 越大越容易被抽到。
- 防重复三层：房间内 `used_task_ids` → 全局最近 30 次使用 → 实在没题了才放宽。
- 赢家可以：`act('redraw')` 换一题 / `input` 自己出题 / 什么都不做（几秒后自动采用题库那题）。
- AI 专属题目（改语气、作诗、送虚拟礼物之类）就在题库里，`target=ai`；
  想加新的，用 MCP 工具 `ai_game_custom_task` 或者直接改 `data/custom_tasks.json`。

**AI 玩真心话大冒险的完整调用链**
1. `ai_game_room(action='join', room_id)` 进房
2. `act('roll')` 摇骰
3. 判定后：
   - 赢了 → 题已经抽好了；想换 `act('redraw')`、想自己出 `input`，都不做就自动采用
   - 输了 → `act('choose', 0真心话|1大冒险)`（会把题目带回来）；真心话 → `input` 回答；大冒险 → `act('do', 1稍后|0已执行)`
   - 旁观 → `view` 看输家选择 / 题目 / 回答
4. 该 AI 说话而它不吽声时，后端只等 5 秒（`AI_IDLE`）就自己推进——不会把房间卡住。''')

add(README, "MCP 工具表加 custom_task",
    r'''| `ai_game_progress(game, room_id)` | 查看本局进度与情况 |''',
    r'''| `ai_game_progress(game, room_id)` | 查看本局进度与情况 |
| `ai_game_custom_task(content, game, target, tags)` | 往题库加一条自定义任务 |''')

add(README, "接口表加 tasks / redraw / use",
    r'''| `POST /api/game/play` | User/AI | 游戏：start / roll / choose / do / input / view / descs / vote … |''',
    r'''| `POST /api/game/play` | User/AI | 游戏：start / roll / choose / do / input / view / descs / redraw / use / vote … |
| `GET /api/game/tasks?game=` | - | 题库统计（真机上核对抽题用） |''')

add(README, "待办段",
    r'''- 聊天记录、房间状态由后端统一管理（与早期"不落库"版本不同）。
- **待完善**：APP 的游戏页面细节（UI / 交互）仍在持续打磨；欢迎 PR。''',
    r'''- 聊天记录、房间状态由后端统一管理（与早期"不落库"版本不同）。
- 每局结束会写一条 `room_history`（房间/赢家/输家/题目/答案），读的接口留到第二批。
- **第二批**：连锁任务（共鸣者）、道具（免死金牌 / 反转骰子）、安全词、`#隐私` 跳过、
  `sanitize_output` 过滤、`room_history` 的读接口。
- **待完善**：谁是卧底的投票阶段还没有超时兜底（投不完会停在 vote）；APP 其他页面细节继续打磨；欢迎 PR。''')


HO = "开发者交接说明.md"

add(HO, "交接说明·本次任务",
    r'''## 六、本次任务
**把 APP 的游戏部分做好**（页面 UI + 交互）。后端和 MCP 工具已可用，APP 目前有了基础页面（`app/lib/game_hall_page.dart` 游戏厅、`spy_room_page.dart`、`truth_room_page.dart`），可在此基础上继续完善。''',
    r'''## 六、本次任务（第一批已完成）
**让真心话大冒险能真玩起来**：后端加题库抽题、人数上限放到 12；前端把 `truth_room_page.dart`
按「环形座位 + 中心书卷」重画，严格按 `phase` 渲染。

### 第一批改了什么

**后端**
- 新增 `tasks.py`（抽题）+ `data/truth.json` / `data/dare.json`（题库）。
- `ROOM_MAX` 8 → **12**。
- `choose` 之后进 `question` 的**同时就把题抽好**（按输家是人是 AI 选 target）。
- 新增 action：`redraw`（赢家换一题）、`use`（赢家就用这题）。
- AI 挂机不吽声时，后端只等 `AI_IDLE`（5 秒）就自己推进，房间不会卡死。
- 作答超时：真心话 60 秒 / 大冒险 90 秒（`ANSWER_TIMEOUT`）。
- 每局结束写一条 `room_history`。
- 修掉一个老 bug：**谁是卧底投票曾占着全局房间锁死等 60 秒**，会把所有房间一起卡住，现在不等了。
- WS 帧统一带上 `ts`：`{"type":"room_update","room_id":..,"ts":..,"room":{..}}`。

**前端**（`app/lib/`）
- `providers/truth_room_provider.dart`  —— 状态层：`ChangeNotifier`，WS + 2 秒轮询 + 本地倒计时。
- `widgets/player_avatar.dart`          —— 座位头像（**金边=真人，蓝边=AI**，赢/输角标，AI 思考中转圈）。
- `widgets/scroll_panel.dart`           —— 中央书卷，`AnimatedSwitcher` 按 `phase` 换内容。
- `widgets/room_theme.dart`             —— 宴会厅那套配色，颜色只在这里写死。
- `truth_room_page.dart`                —— 重写：环形座位 + 中心书卷 + 底部可折叠「我的信息」。
- `api.dart`                            —— 加 `gamePlay` / `taskStats` / `wsUrlFor`。
- `game_hall_page.dart`                 —— 人数选项 3~12；下拉框换成新老 Flutter 都能编的写法。

> 前端**没有**引入 Riverpod / Bloc：加依赖就多一个我这边没法验证的失败点，
> 用 Flutter 自带的 `ChangeNotifier` 做到同样的事。要换 Riverpod 随时说。

### 渲染必须守的两条
1. **看 `phase`，不看 `status`**。`status` 只有 waiting/playing/ended；
   `phase` 才是 waiting/roll/choose/question/answer/result。
2. **房间全量状态从 `/api/game/room` 的 `action:status` 拿**，不要用 `view`
   ——`view` 只返回你自己的点数/身份，没有 players。''')


def main():
    for path, reps in P.items():
        s = open(path, encoding="utf-8").read()
        bad = []
        for desc, old, new in reps:
            n = s.count(old)
            if n != 1:
                bad.append((desc, n))
                continue
            s = s.replace(old, new, 1)
        if bad:
            print("!!", path, "匹配不对：")
            for d, n in bad:
                print("   -", d, "出现", n, "次")
            return 1
        open(path, "w", encoding="utf-8").write(s)
        print("OK", path, len(reps), "处")
    return 0


sys.exit(main())
