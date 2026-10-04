# -*- coding: utf-8 -*-
"""第一批·前端补丁：改 api.dart / game_hall_page.dart / home_page.dart / settings_page.dart。
在仓库根目录跑（python3 patch/20261004b-app.py）。
每处替换校对出现次数，对不上就整体不动。
"""
import sys

P = {}


def add(path, desc, old, new):
    P.setdefault(path, []).append((desc, old, new))


# ---------------- api.dart ----------------
add("app/lib/api.dart", "游戏操作统一入口 gamePlay + taskStats + wsUrlFor",
    r'''  // 真心话大冒险
  static Future<Map<String, dynamic>> truthOp(String roomId, String action,
          String userKey, {String choice = '', String text = ''}) =>
      post('/api/game/play',
          {'action': action, 'room_id': roomId, 'choice': choice, 'text': text},
          userKey: userKey);
}''',
    r'''  // 真心话大冒险
  static Future<Map<String, dynamic>> truthOp(String roomId, String action,
          String userKey, {String choice = '', String text = ''}) =>
      gamePlay(roomId, action, userKey, choice: choice, text: text);

  /// 游戏操作统一入口（真心话 / 谁是卧底都走它）。
  ///
  /// action：start / roll / choose / do / input / view / descs / redraw / use / vote …
  /// 只有真人玩家会调它——AI 由后端 MCP 驱动，前端不为 AI 发请求。
  static Future<Map<String, dynamic>> gamePlay(String roomId, String action,
          String userKey,
          {String choice = '', String text = '', String target = ''}) =>
      post(
        '/api/game/play',
        {
          'action': action,
          'room_id': roomId,
          'choice': choice,
          'text': text,
          'target': target,
        },
        userKey: userKey,
      );

  /// 题库统计（真机上排查抽题用）
  static Future<Map<String, dynamic>> taskStats(String userKey,
          {String game = 'truth'}) =>
      get('/api/game/tasks', userKey: userKey, q: {'game': game});

  /// 房间 WebSocket 地址。房间页用它听 `room_update` 帧：
  /// {"type":"room_update","room_id":"...","ts":...,"room":{ …全量… }}
  static String wsUrlFor(String userKey) =>
      base.replaceFirst('http', 'ws') + '/ws?user_key=' + userKey;
}''')

# ---------------- game_hall_page.dart ----------------
add("app/lib/game_hall_page.dart", "游戏下拉框换写法",
    r'''              DropdownButtonFormField<String>(
                value: game,
                items: _games
                    .map((x) => DropdownMenuItem<String>(value: x['id'] as String, child: Text(x['name'] as String)))
                    .toList(),
                onChanged: (v) { if (v != null) { game = v; st(() {}); } },
                decoration: const InputDecoration(labelText: '游戏'),
              ),''',
    r'''              // 用 InputDecorator + DropdownButton：新老 Flutter 都稳
              // （FormField 那一版的 value 参数在新版里改名了，留着容易编译不过）
              InputDecorator(
                decoration: const InputDecoration(labelText: '游戏'),
                child: DropdownButton<String>(
                  value: game,
                  isExpanded: true,
                  underline: const SizedBox.shrink(),
                  items: _games
                      .map((x) => DropdownMenuItem<String>(value: x['id'] as String, child: Text(x['name'] as String)))
                      .toList(),
                  onChanged: (v) { if (v != null) { game = v; st(() {}); } },
                ),
              ),''')

add("app/lib/game_hall_page.dart", "人数下拉框 3~12",
    r'''              DropdownButtonFormField<int>(
                value: maxP,
                items: [3, 4, 5, 6]
                    .map((x) => DropdownMenuItem(value: x, child: Text('$x 人')))
                    .toList(),
                onChanged: (v) { if (v != null) { maxP = v; st(() {}); } },
                decoration: const InputDecoration(labelText: '房间人数'),
              ),''',
    r'''              InputDecorator(
                decoration: const InputDecoration(labelText: '房间人数'),
                child: DropdownButton<int>(
                  value: maxP,
                  isExpanded: true,
                  underline: const SizedBox.shrink(),
                  // 后端 ROOM_MAX 已经放开到 12
                  items: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
                      .map((x) => DropdownMenuItem(value: x, child: Text('$x 人')))
                      .toList(),
                  onChanged: (v) { if (v != null) { maxP = v; st(() {}); } },
                ),
              ),''')

add("app/lib/game_hall_page.dart", "真心话规则文案",
    r'''      'rule': '2人以上。全员摇骰子，点数最大=赢家、最小=输家。输家选真心话或大冒险，赢家出题，输家回答/执行。超时自动跳过，开局后不能加入。',''',
    r'''      'rule': '2人以上。全员摇骰子，点数最大=赢家、最小=输家。输家选真心话或大冒险，题目由题库自动抽（赢家也能自己出），输家回答/执行。超时自动跳过，开局后不能加入。',''')

add("app/lib/game_hall_page.dart", "withOpacity 换掉",
    r'''            side: BorderSide(color: Colors.black.withOpacity(0.3))),''',
    r'''            side: const BorderSide(color: Color.fromRGBO(0, 0, 0, 0.3))),''')

# ---------------- home_page.dart ----------------
add("app/lib/home_page.dart", "withOpacity 换掉（黑87）",
    r'''Colors.black87.withOpacity(0.3)''',
    r'''Color.fromRGBO(0, 0, 0, 0.26)''')

add("app/lib/home_page.dart", "withOpacity 换掉（黑）",
    r'''Colors.black.withOpacity(0.3)''',
    r'''Color.fromRGBO(0, 0, 0, 0.3)''')

# ---------------- settings_page.dart ----------------
add("app/lib/settings_page.dart", "withOpacity 换掉",
    r'''Colors.black.withOpacity(0.3)''',
    r'''Color.fromRGBO(0, 0, 0, 0.3)''')


def main():
    total = 0
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
            print("!!", path, "匹配不对，这个文件不动：")
            for d, n in bad:
                print("   -", d, "出现", n, "次")
            return 1
        if "withOpacity" in s:
            print("!!", path, "还有 withOpacity 没换干净")
            return 1
        open(path, "w", encoding="utf-8").write(s)
        total += len(reps)
        print("OK", path, len(reps), "处")
    print("共 %d 处" % total)
    return 0


sys.exit(main())
