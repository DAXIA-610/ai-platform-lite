import 'dart:convert';
import 'package:http/http.dart' as http;

/// 统一的后端 API 封装。后端地址写死为局域网地址。
class Api {
  static String base = "http://192.168.1.251:8000";

  static String wsUrl() => base.replaceFirst('http', 'ws') + '/ws';

  static Future<Map<String, dynamic>> post(String path, Map body,
      {String? userKey, String? aiKey}) async {
    final h = {'Content-Type': 'application/json'};
    if (userKey != null) h['X-User-Key'] = userKey;
    if (aiKey != null) h['X-AI-Key'] = aiKey;
    final r = await http.post(Uri.parse(base + path),
        headers: h, body: jsonEncode(body));
    return jsonDecode(r.body);
  }

  static Future<Map<String, dynamic>> get(String path,
      {String? userKey, String? aiKey, Map<String, String>? q}) async {
    final h = <String, String>{};
    if (userKey != null) h['X-User-Key'] = userKey;
    if (aiKey != null) h['X-AI-Key'] = aiKey;
    var url = base + path;
    if (q != null && q.isNotEmpty) {
      url += "?" + q.entries.map((e) => "${e.key}=${e.value}").join("&");
    }
    final r = await http.get(Uri.parse(url), headers: h);
    return jsonDecode(r.body);
  }

  // ---- 账号 ----
  static Future<Map<String, dynamic>> register(String name, String password) =>
      post('/api/register', {'name': name, 'password': password});
  static Future<Map<String, dynamic>> login(String uid, String password) =>
      post('/api/login', {'user_id': uid, 'password': password});

  // ---- AI ----
  static Future<Map<String, dynamic>> addAI(String name, String userKey) =>
      post('/api/ai/add', {'name': name}, userKey: userKey);
  static Future<Map<String, dynamic>> listAI(String userKey) =>
      get('/api/ai/list', userKey: userKey);

  // ---- 工具(AI 操作) ----
  static Future<Map<String, dynamic>> friends(String userKey, String aiKey) =>
      get('/api/tool/friends', userKey: userKey, aiKey: aiKey);
  static Future<Map<String, dynamic>> addFriend(String target, String userKey,
          String aiKey) =>
      post('/api/tool/add_friend', {'target': target},
          userKey: userKey, aiKey: aiKey);
  static Future<Map<String, dynamic>> accept(String from, String userKey,
          String aiKey) =>
      post('/api/tool/accept', {'from': from}, userKey: userKey, aiKey: aiKey);
  static Future<Map<String, dynamic>> send(String to, String message,
          String userKey, String aiKey) =>
      post('/api/tool/send', {'to': to, 'message': message},
          userKey: userKey, aiKey: aiKey);
  static Future<Map<String, dynamic>> read(String userKey, String aiKey) =>
      get('/api/tool/read', userKey: userKey, aiKey: aiKey);

  // ---- 游戏：房间 ----
  static Future<Map<String, dynamic>> roomCreate(String name, String game,
          int maxPlayers, String userKey) =>
      post('/api/game/room',
          {'action': 'create', 'name': name, 'game': game, 'max_players': maxPlayers},
          userKey: userKey);
  static Future<Map<String, dynamic>> roomJoin(String roomId, String userKey) =>
      post('/api/game/room', {'action': 'join', 'room_id': roomId}, userKey: userKey);
  static Future<Map<String, dynamic>> roomLeave(String roomId, String userKey) =>
      post('/api/game/room', {'action': 'leave', 'room_id': roomId}, userKey: userKey);
  static Future<Map<String, dynamic>> roomClose(String roomId, String userKey) =>
      post('/api/game/room', {'action': 'close', 'room_id': roomId}, userKey: userKey);
  static Future<Map<String, dynamic>> roomStatus(String roomId, String userKey) =>
      post('/api/game/room', {'action': 'status', 'room_id': roomId}, userKey: userKey);

  // 游戏操作
  static Future<Map<String, dynamic>> gameStart(String roomId, String userKey) =>
      post('/api/game/play', {'action': 'start', 'room_id': roomId}, userKey: userKey);
  static Future<Map<String, dynamic>> gameMyCard(String roomId, String userKey) =>
      post('/api/game/play', {'action': 'my_card', 'room_id': roomId}, userKey: userKey);
  static Future<Map<String, dynamic>> gameSpeak(
          String roomId, String text, String userKey) =>
      post('/api/game/play',
          {'action': 'speak', 'room_id': roomId, 'text': text}, userKey: userKey);
  static Future<Map<String, dynamic>> gameVote(
          String roomId, String target, String userKey) =>
      post('/api/game/play',
          {'action': 'vote', 'room_id': roomId, 'target': target}, userKey: userKey);
  static Future<Map<String, dynamic>> gameReveal(String roomId, String userKey) =>
      post('/api/game/play', {'action': 'reveal', 'room_id': roomId}, userKey: userKey);
}
