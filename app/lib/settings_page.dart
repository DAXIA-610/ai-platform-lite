import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api.dart';

class SettingsPage extends StatefulWidget {
  final String userKey;
  final String userName;
  final Future<void> Function() onChanged;
  const SettingsPage({super.key, required this.userKey,
      required this.userName, required this.onChanged});
  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  String _name = '';

  @override
  void initState() {
    super.initState();
    _name = widget.userName;
  }

  Future<void> _rename() async {
    final c = TextEditingController(text: _name);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('修改昵称'),
        content: TextField(controller: c),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('保存')),
        ],
      ),
    );
    if (ok != true || c.text.trim().isEmpty) return;
    final p = await SharedPreferences.getInstance();
    await p.setString('user_name', c.text.trim());
    setState(() => _name = c.text.trim());
    await widget.onChanged();
    if (mounted) Navigator.pop(context);
  }

  Future<void> _pwd() async {
    final o = TextEditingController();
    final n = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('修改密码'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: o, obscureText: true, decoration: const InputDecoration(labelText: '原密码')),
          TextField(controller: n, obscureText: true, decoration: const InputDecoration(labelText: '新密码')),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('保存')),
        ],
      ),
    );
    if (ok != true) return;
    final r = await Api.accountPassword(o.text, n.text, widget.userKey);
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(r['ok'] == true ? '密码已改' : (r['error'] ?? '失败'))));
    }
  }

  Future<void> _clearLocal() async {
    final p = await SharedPreferences.getInstance();
    final keys = p.getKeys().where((k) => k.startsWith('chat_')).toList();
    for (final k in keys) { await p.remove(k); }
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('已清除本地记录')));
    }
  }

  Future<void> _logout() async {
    final p = await SharedPreferences.getInstance();
    await p.remove('user_key');
    if (context.mounted) {
      Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const _Out()), (r) => false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF2F2F2),
      appBar: AppBar(backgroundColor: Colors.white, foregroundColor: Colors.black,
          title: const Text('设置')),
      body: ListView(padding: const EdgeInsets.all(12), children: [
        _row(Icons.badge, '修改昵称', '当前：$_name', _rename),
        _row(Icons.lock, '修改密码', '更换登录密码', _pwd),
        _row(Icons.delete_sweep, '清除本地记录', '删掉本机聊天缓存', _clearLocal),
        _row(Icons.logout, '退出登录', '返回登录页', _logout),
      ]),
    );
  }

  Widget _row(IconData ic, String t, String sub, VoidCallback onTap) {
    return Padding(padding: const EdgeInsets.only(bottom: 8), child: InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(color: Colors.white,
            border: Border.all(color: Colors.black.withOpacity(0.3)),
            borderRadius: BorderRadius.circular(14)),
        child: Row(children: [
          Container(width: 34, height: 34,
              decoration: BoxDecoration(color: Colors.black, borderRadius: BorderRadius.circular(9)),
              child: Icon(ic, color: Colors.white, size: 18)),
          const SizedBox(width: 12),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(t, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: Colors.black)),
            Text(sub, style: const TextStyle(fontSize: 12, color: Colors.grey)),
          ])),
          const Icon(Icons.chevron_right, color: Colors.black26),
        ]),
      ),
    ));
  }
}

class _Out extends StatelessWidget {
  const _Out();
  @override
  Widget build(BuildContext c) => const Scaffold(body: Center(child: Text('已退出')));
}
