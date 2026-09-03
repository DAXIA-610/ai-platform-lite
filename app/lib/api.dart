import 'dart:convert';
import 'package:http/http.dart' as http;

/// 统一的后端 API 封装。base 可在登录页由用户填（默认指向本机）。
class Api {
  static String base = "http://127.0.0.1:8000";

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
    final h = {};
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
}
