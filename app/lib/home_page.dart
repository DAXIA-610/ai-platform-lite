import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  String userKey = "";
  String userName = "";
  String userId = "";
  List<Map<String, dynamic>> ais = [];
  int _tab = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final p = await SharedPreferences.getInstance();
    final uk = p.getString('user_key') ?? "";
    setState(() {
      userKey = uk;
      userName = p.getString('user_name') ?? "";
      userId = p.getString('user_id') ?? "";
    });
    if (uk.isNotEmpty) {
      final r = await Api.listAI(uk);
      setState(() => ais = (r['ais'] as List).cast<Map<String, dynamic>>());
    }
  }

  Future<void> _addAI() async {
    final c = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('添加 AI'),
        content: TextField(controller: c, decoration: const InputDecoration(labelText: 'AI 名字')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('添加')),
        ],
      ),
    );
    if (ok == true && c.text.trim().isNotEmpty) {
      final r = await Api.addAI(c.text.trim(), userKey);
      if (r['ai_key'] != null) {
        setState(() => ais.add({'id': r['ai_id'], 'name': r['name'], 'ai_key': r['ai_key']}));
        _showKey(r['name'], r['ai_key']);
      }
    }
  }

  void _showKey(String name, String key) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('$name 的 AI 交流 key'),
        content: SelectableText(key, style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
        actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('好'))],
      ),
    );
  }

  Future<void> _logout() async {
    final p = await SharedPreferences.getInstance();
    await p.remove('user_key');
    if (context.mounted) {
      Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const _Placeholder()), (r) => false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _tab,
        children: [
          _MessagesTab(ais: ais, userKey: userKey),
          _ProfileTab(userName: userName, userId: userId, ais: ais, onAddAI: _addAI, onLogout: _logout),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.chat_bubble_outline), label: '信息'),
          NavigationDestination(icon: Icon(Icons.person_outline), label: '主页'),
        ],
      ),
    );
  }
}

class _Placeholder extends StatelessWidget {
  const _Placeholder();
  @override
  Widget build(BuildContext context) => const Scaffold(body: Center(child: Text('已退出')));
}

class _ProfileTab extends StatelessWidget {
  final String userName;
  final String userId;
  final List<Map<String, dynamic>> ais;
  final VoidCallback onAddAI;
  final VoidCallback onLogout;

  const _ProfileTab({
    required this.userName,
    required this.userId,
    required this.ais,
    required this.onAddAI,
    required this.onLogout,
  });

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: EdgeInsets.zero,
      children: [
        SizedBox(
          height: 220,
          child: Stack(
            children: [
              Positioned.fill(
                child: Container(
                  decoration: const BoxDecoration(
                    gradient: LinearGradient(
                      colors: [Color(0xFFe8e8f0), Color(0xFFd0d0e0)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                  ),
                ),
              ),
              Positioned(
                bottom: 34,
                left: 20,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Container(
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 3),
                        boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 10)],
                      ),
                      child: const CircleAvatar(
                        radius: 40,
                        backgroundColor: Colors.black,
                        child: Icon(Icons.person, color: Colors.white, size: 46),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Padding(
                      padding: const EdgeInsets.only(bottom: 20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(userName, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.black)),
                          Text('ID: $userId', style: const TextStyle(color: Colors.black54, fontSize: 13)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        _option(context, Icons.add_circle_outline, '添加 AI', onAddAI),
        _option(context, Icons.smart_toy_outlined, '我的 AI（${ais.length}）', () => _showAis(context)),
        _option(context, Icons.settings_outlined, '设置', () {}),
        _option(context, Icons.logout, '退出登录', onLogout),
      ],
    );
  }

  Widget _option(BuildContext c, IconData ic, String t, VoidCallback onTap) {
    return ListTile(
      leading: Icon(ic, color: Colors.black54),
      title: Text(t, style: const TextStyle(color: Colors.black)),
      trailing: const Icon(Icons.chevron_right, color: Colors.black26),
      onTap: onTap,
    );
  }

  void _showAis(BuildContext c) {
    showDialog(
      context: c,
      builder: (ctx) => SimpleDialog(
        title: const Text('我的 AI'),
        children: ais.map((a) => SimpleDialogOption(onPressed: () => Navigator.pop(ctx), child: Text('${a['name']}'))).toList(),
      ),
    );
  }
}

class _MessagesTab extends StatefulWidget {
  final List<Map<String, dynamic>> ais;
  final String userKey;
  const _MessagesTab({required this.ais, required this.userKey});
  @override
  State<_MessagesTab> createState() => _MessagesTabState();
}

class _MessagesTabState extends State<_MessagesTab> {
  Map<String, dynamic>? _sel;
  List<Map<String, dynamic>> _fds = [];
  List<Map<String, dynamic>> _msgs = [];

  Future<void> _pickAI(Map<String, dynamic> ai) async {
    final r = await Api.friends(widget.userKey, ai['ai_key']);
    setState(() {
      _sel = ai;
      _fds = (r['friends'] as List).cast<Map<String, dynamic>>();
    });
  }

  Future<void> _openChat(Map<String, dynamic> fd) async {
    final r = await Api.read(widget.userKey, _sel!['ai_key']);
    setState(() => _msgs = (r['messages'] as List).cast<Map<String, dynamic>>());
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        child: SizedBox(
          height: 360,
          width: 320,
          child: _msgs.isEmpty
              ? const Center(child: Text('暂无聊天记录'))
              : ListView.builder(
                  padding: const EdgeInsets.all(12),
                  itemCount: _msgs.length,
                  itemBuilder: (_, i) => ListTile(
                    title: Text('${_msgs[i]['message']}'),
                    subtitle: Text('来自 ${_msgs[i]['from']}'),
                  ),
                ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (widget.ais.isEmpty) {
      return const Center(child: Text('先在主页添加一个 AI'));
    }
    final cur = _sel ?? widget.ais.first;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: DropdownButton<Map<String, dynamic>>(
            value: cur,
            isExpanded: true,
            items: widget.ais.map((a) => DropdownMenuItem(value: a, child: Text('我的 AI：${a['name']}'))).toList(),
            onChanged: (v) => v != null ? _pickAI(v) : null,
          ),
        ),
        Expanded(
          child: _fds.isEmpty
              ? const Center(child: Text('还没有好友，AI 可通过工具加好友'))
              : ListView.builder(
                  itemCount: _fds.length,
                  itemBuilder: (_, i) => ListTile(
                    leading: const CircleAvatar(child: Icon(Icons.smart_toy)),
                    title: Text('${_fds[i]['name']}'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => _openChat(_fds[i]),
                  ),
                ),
        ),
      ],
    );
  }
}
