import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api.dart';
import 'home_page.dart';

// ---------- 登录页 ----------
class LoginPage extends StatefulWidget {
  const LoginPage({super.key});
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _uid = TextEditingController();
  final _pwd = TextEditingController();
  String _err = "";

  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((p) {
      if ((p.getString('user_key') ?? '').isNotEmpty && mounted) {
        Navigator.of(context).pushReplacement(
            MaterialPageRoute(builder: (_) => const HomePage()));
      }
    });
  }

  Future<void> _login() async {
    setState(() => _err = "");
    try {
      final r = await Api.login(_uid.text.trim(), _pwd.text);
      if (r['user_key'] != null) {
        final p = await SharedPreferences.getInstance();
        await p.setString('user_key', r['user_key']);
        await p.setString('user_id', '${r['user_id']}');
        await p.setString('user_name', r['name']);
        if (mounted) {
          Navigator.of(context).pushReplacement(
              MaterialPageRoute(builder: (_) => const HomePage()));
        }
      } else {
        setState(() => _err = r['error']?.toString() ?? '登录失败');
      }
    } catch (e) {
      setState(() => _err = '连不上后端：$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Icon(Icons.smart_toy, size: 72, color: Colors.black),
                const SizedBox(height: 16),
                const Text('AI 社交平台',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Colors.black)),
                const SizedBox(height: 40),
                TextField(
                  controller: _uid,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: '账号',
                    border: OutlineInputBorder(),
                    prefixIcon: Icon(Icons.person_outline),
                  ),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _pwd,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: '密码',
                    border: OutlineInputBorder(),
                    prefixIcon: Icon(Icons.lock_outline),
                  ),
                ),
                if (_err.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(_err, style: const TextStyle(color: Colors.red)),
                ],
                const SizedBox(height: 24),
                FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: Colors.black,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  onPressed: _login,
                  child: const Text('登录'),
                ),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: () {
                    Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => const RegisterPage()));
                  },
                  child: const Text('没有账号？点击注册'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ---------- 注册页 ----------
class RegisterPage extends StatefulWidget {
  const RegisterPage({super.key});
  @override
  State<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends State<RegisterPage> {
  final _name = TextEditingController();
  final _pwd = TextEditingController();
  String _err = "";
  String _ok = "";

  Future<void> _register() async {
    setState(() { _err = ""; _ok = ""; });
    try {
      final r = await Api.register(_name.text.trim(), _pwd.text);
      if (r['user_id'] != null) {
        setState(() => _ok = '注册成功，你的用户ID是 ${r['user_id']}，请回登录页登录');
      } else {
        setState(() => _err = r['error']?.toString() ?? '注册失败');
      }
    } catch (e) {
      setState(() => _err = '连不上后端：$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('注册')),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  controller: _name,
                  decoration: const InputDecoration(
                    labelText: '你的名字',
                    border: OutlineInputBorder(),
                    prefixIcon: Icon(Icons.person_outline),
                  ),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _pwd,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: '密码',
                    border: OutlineInputBorder(),
                    prefixIcon: Icon(Icons.lock_outline),
                  ),
                ),
                if (_err.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(_err, style: const TextStyle(color: Colors.red)),
                ],
                if (_ok.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(_ok, style: const TextStyle(color: Colors.green)),
                ],
                const SizedBox(height: 24),
                FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: Colors.black,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  onPressed: _register,
                  child: const Text('注册'),
                ),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('已有账号？返回登录'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
