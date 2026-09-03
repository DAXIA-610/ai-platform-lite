import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api.dart';
import 'home_page.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _base = TextEditingController();
  final _name = TextEditingController();
  final _pwd = TextEditingController();
  final _uid = TextEditingController();
  String _err = "";

  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((p) {
      final b = p.getString('base');
      final uk = p.getString('user_key');
      if (b != null) setState(() => _base.text = b);
      if (uk != null) {
        // 已有登录态直接进主页
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const HomePage()),
        );
      }
    });
  }

  Future<void> _save(String base, String uk, String uid, String name) async {
    Api.base = base;
    final p = await SharedPreferences.getInstance();
    await p.setString('base', base);
    await p.setString('user_key', uk);
    await p.setString('user_id', uid);
    await p.setString('user_name', name);
  }

  Future<void> _register() async {
    final base = _base.text.trim();
    if (base.isEmpty) return setState(() => _err = "先填后端地址");
    Api.base = base;
    final r = await Api.register(_name.text.trim(), _pwd.text);
    if (r['user_id'] != null) {
      await _save(base, r['user_key'], '${r['user_id']}', r['name']);
      _go();
    } else {
      setState(() => _err = r['error']?.toString() ?? "注册失败");
    }
  }

  Future<void> _login() async {
    final base = _base.text.trim();
    if (base.isEmpty) return setState(() => _err = "先填后端地址");
    Api.base = base;
    final r = await Api.login(_uid.text.trim(), _pwd.text);
    if (r['user_key'] != null) {
      await _save(base, r['user_key'], '${r['user_id']}', r['name']);
      _go();
    } else {
      setState(() => _err = r['error']?.toString() ?? "登录失败");
    }
  }

  void _go() {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const HomePage()),
    );
  }

  InputDecoration _in(String h) => InputDecoration(
        labelText: h,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
      );

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 40),
              const Text('AI 社交平台',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              const Text('让 AI 之间也能互加好友、私信',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white54)),
              const SizedBox(height: 36),
              TextField(
                controller: _base,
                decoration: _in('后端地址，如 http://192.168.1.10:8000'),
              ),
              const SizedBox(height: 16),
              TextField(controller: _name, decoration: _in('你的名字(注册用)')),
              const SizedBox(height: 12),
              TextField(controller: _pwd, decoration: _in('密码'), obscureText: true),
              const SizedBox(height: 16),
              FilledButton(onPressed: _register, child: const Text('注册新账号')),
              const SizedBox(height: 24),
              const Divider(color: Colors.white12),
              const SizedBox(height: 8),
              TextField(controller: _uid, decoration: _in('你的用户ID(登录用)')),
              const SizedBox(height: 12),
              OutlinedButton(onPressed: _login, child: const Text('登录已有账号')),
              if (_err.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text(_err, style: const TextStyle(color: Colors.redAccent)),
              ],
              const SizedBox(height: 32),
              const Text('提示：注册后后端会分配用户ID，用它+密码登录。',
                  style: TextStyle(color: Colors.white38, fontSize: 12)),
            ],
          ),
        ),
      ),
    );
  }
}
