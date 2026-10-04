import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../api.dart';

/// 真心话大冒险房间的状态层。
///
/// 只做三件事：
///   1. 拉全量房间状态（`/api/game/room` 的 `action:status`）——书卷只按它渲染；
///   2. 听 WebSocket 的 `room_update` 帧；
///   3. 跑本地倒计时，归零后重新拉一次。
///
/// 两条硬规矩：
///   · **渲染看 `phase`，不看 `status`**。`status` 只有 waiting/playing/ended，
///     真正决定书卷内容的是 `phase`（waiting/roll/choose/question/answer/result）。
///   · **前端永远不为 AI 发请求**。真人用 `X-User-Key` 操作；AI 由后端 MCP 驱动，
///     前端只负责把它的状态画出来。
class TruthRoomProvider extends ChangeNotifier {
  TruthRoomProvider({
    required this.roomId,
    required this.userKey,
    required this.userId,
  }) {
    _start();
  }

  final String roomId;
  final String userKey;
  final String userId;

  /// 后端返回的全量房间对象（players / rolls / winner / loser / phase / …）
  Map<String, dynamic>? room;

  bool loading = true;

  /// 请求进行中：按钮点一下就置灰。请求回来（或失败）就解锁。
  /// 至于“这个按钮现在该不该出现”，一律由 phase + 数据决定（比如摇过骰子
  /// 之后 myPoint 不为空，按钮自己就换成了等待文案），不靠这个标志。
  bool busy = false;

  /// 最后一次错误（页面底部弹一下就好）
  String? error;

  /// 本地倒计时（秒）。只在本阶段**第一次**看到时重置，刷新不会把它冲掉。
  int countdown = 0;

  /// 连续拉不到房间的次数，够 3 次就认为房间散了
  int miss = 0;

  /// 底部“我的信息”折叠区
  bool showPrivate = false;

  Timer? _poll;
  Timer? _tick;
  WebSocket? _ws;
  bool _disposed = false;
  String? _lastPhase;

  /// 各阶段的倒计时长度（跟后端超时保持一致）
  static const Map<String, int> _phaseSeconds = {
    'roll': 60,
    'choose': 60,
    'question': 90,
  };

  // ==================== 生命周期 ====================

  void _start() {
    refresh();
    _poll = Timer.periodic(const Duration(seconds: 2), (_) => refresh(silent: true));
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (countdown > 0) {
        countdown--;
        notifyListeners();
      }
    });
    _connectWs();
  }

  @override
  void dispose() {
    _disposed = true;
    _poll?.cancel();
    _tick?.cancel();
    _ws?.close();
    super.dispose();
  }

  void clearError() {
    if (error != null) {
      error = null;
      notifyListeners();
    }
  }

  void togglePrivate() {
    showPrivate = !showPrivate;
    notifyListeners();
  }

  // ==================== 拉取 ====================

  Future<void> refresh({bool silent = false}) async {
    if (_disposed) return;
    try {
      final r = await Api.roomStatus(roomId, userKey);
      if (_disposed) return;
      final got = r['room'];
      if (got is Map) {
        miss = 0;
        _applyRoom(Map<String, dynamic>.from(got));
      } else {
        miss++;
        if (miss >= 3) error = '房间已解散';
      }
    } catch (e) {
      if (!silent) error = '连不上服务器';
    } finally {
      if (!_disposed) {
        loading = false;
        notifyListeners();
      }
    }
  }

  /// 房间数据统一从这里进。phase 一变就重置倒计时。
  void _applyRoom(Map<String, dynamic> r) {
    final ph = (r['phase'] ?? 'waiting').toString();
    if (ph != _lastPhase) {
      _lastPhase = ph;
      countdown = _secondsFor(ph);
    }
    room = r;
    if (!_disposed) notifyListeners();
  }

  int _secondsFor(String ph) {
    if (ph == 'answer') return loserChoice == 'dare' ? 90 : 60;
    return _phaseSeconds[ph] ?? 0;
  }

  // ==================== WebSocket ====================
  // 后端推的帧长这样（实测）：
  //   {"type":"room_update","room_id":"862054","ts":1791...,"room":{ …全量… }}

  void _connectWs() {
    if (_disposed) return;
    try {
      WebSocket.connect(Api.wsUrlFor(userKey)).then((ws) {
        if (_disposed) {
          ws.close();
          return;
        }
        _ws = ws;
        ws.listen(
          (data) {
            try {
              final m = jsonDecode(data as String);
              if (m is Map &&
                  m['type'] == 'room_update' &&
                  m['room_id'] == roomId &&
                  m['room'] is Map) {
                loading = false;
                _applyRoom(Map<String, dynamic>.from(m['room']));
              }
            } catch (_) {/* 不是我们能认的帧，丢掉 */}
          },
          onError: (_) {},
          onDone: () {
            _ws = null;
            _retryWs();
          },
        );
      }).catchError((_) => _retryWs());
    } catch (_) {
      _retryWs();
    }
  }

  void _retryWs() {
    if (_disposed) return;
    Timer(const Duration(seconds: 3), () {
      if (!_disposed) _connectWs();
    });
  }

  // ==================== 操作 ====================

  /// 统一入口，只发真人自己的操作。
  Future<bool> act(
    String action, {
    String choice = '',
    String text = '',
    String target = '',
  }) async {
    if (busy) return false;
    busy = true;
    notifyListeners();
    var ok = false;
    try {
      final r = await Api.gamePlay(roomId, action, userKey,
          choice: choice, text: text, target: target);
      if (r['ok'] == true) {
        ok = true;
      } else {
        error = (r['error'] ?? '操作失败').toString();
      }
      await refresh(silent: true);
    } catch (e) {
      error = '网络错误';
    } finally {
      busy = false;
      if (!_disposed) notifyListeners();
    }
    return ok;
  }

  // ==================== 派生字段（页面只读这些） ====================

  String get phase => (room?['phase'] ?? 'waiting').toString();
  String get status => (room?['status'] ?? 'waiting').toString();
  int get round => _intOf(room?['round']);
  String? get question => room?['question']?.toString();
  String? get answer => room?['answer']?.toString();
  String? get dare => room?['dare']?.toString();
  String? get loserChoice => room?['loser_choice']?.toString();
  String? get taskId => room?['task_id']?.toString();
  String get roomName => (room?['name'] ?? '房间').toString();
  int get maxPlayers => _intOf(room?['max_players']);
  String? get result => room?['result']?.toString();

  List<Map<String, dynamic>> get players => _listOf(room?['players']);
  List<Map<String, dynamic>> get rolls => _listOf(room?['rolls']);

  Map<String, dynamic>? get me {
    for (final p in players) {
      if (p['is_ai'] != true && '${p['uid']}' == userId) return p;
    }
    return null;
  }

  bool get isHost => me?['host'] == true;

  bool get isWinner {
    final m = me;
    return m != null && matchesKey(room?['winner'], m);
  }

  bool get isLoser {
    final m = me;
    return m != null && matchesKey(room?['loser'], m);
  }

  int? get myPoint {
    final m = me;
    return m == null ? null : pointOf(m);
  }

  Map<String, dynamic>? get winnerPlayer => _byKey(room?['winner']);
  Map<String, dynamic>? get loserPlayer => _byKey(room?['loser']);

  /// 玩家 key 是 `["a", ai_id]` / `["u", uid]`——实测就是这样，不是对象。
  static bool matchesKey(dynamic key, Map p) {
    if (key is! List || key.length < 2) return false;
    if (key[0] == 'a') {
      return p['is_ai'] == true && '${p['ai_id']}' == '${key[1]}';
    }
    return p['is_ai'] != true && '${p['uid']}' == '${key[1]}';
  }

  int? pointOf(Map p) {
    for (final it in rolls) {
      if (matchesKey(it['k'], p)) return _intOf(it['v']);
    }
    return null;
  }

  Map<String, dynamic>? _byKey(dynamic key) {
    for (final p in players) {
      if (matchesKey(key, p)) return p;
    }
    return null;
  }

  /// 这一阶段该谁动（用来给头像加“行动中”高亮）
  bool isActing(Map p) {
    switch (phase) {
      case 'choose':
      case 'answer':
        return isLoserP(p);
      case 'question':
        return isWinnerP(p);
      case 'roll':
        return pointOf(p) == null;
      default:
        return false;
    }
  }

  bool isWinnerP(Map p) => matchesKey(room?['winner'], p);
  bool isLoserP(Map p) => matchesKey(room?['loser'], p);

  /// AI 在“轮到自己但还没动作”时显示“AI 思考中”。
  /// 后端不会告诉前端它在想什么，这里只按 phase + 数据推。
  bool isAiThinking(Map p) {
    if (p['is_ai'] != true) return false;
    switch (phase) {
      case 'roll':
        return pointOf(p) == null;
      case 'choose':
        return isLoserP(p) && loserChoice == null;
      case 'question':
        return isWinnerP(p);
      case 'answer':
        return isLoserP(p) && answer == null && dare == null;
      default:
        return false;
    }
  }

  // ==================== 小工具 ====================

  static int _intOf(dynamic v) {
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.tryParse('$v') ?? 0;
  }

  static List<Map<String, dynamic>> _listOf(dynamic v) {
    if (v is List) {
      return v.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
    }
    return const [];
  }
}
