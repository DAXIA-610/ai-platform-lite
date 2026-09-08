import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api.dart';
import 'chat_page.dart';
import 'game_hall_page.dart';
import 'settings_page.dart';

Future<String> _pickImageBase64() async {
  final x = await ImagePicker().pickImage(
      source: ImageSource.gallery, maxWidth: 300, imageQuality: 70);
  if (x == null) return '';
  return 'data:image/jpeg;base64,' + base64Encode(await x.readAsBytes());
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  String userKey = "", userName = "", userId = "", userAv = "";
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
      userAv = p.getString('u_av') ?? "";
    });
    if (uk.isNotEmpty) {
      final r = await Api.listAI(uk);
      setState(() => ais = (r['ais'] as List).cast<Map<String, dynamic>>());
    }
  }

  Future<void> _pickUserAv() async {
    final b = await _pickImageBase64();
    if (b.isEmpty) return;
    final p = await SharedPreferences.getInstance();
    await p.setString('u_av', b);
    setState(() => userAv = b);
  }

  Widget _av(String? img, String name, double r) {
    if (img != null && img.isNotEmpty && img.length > 4) {
      return CircleAvatar(radius: r, backgroundColor: Colors.black,
          backgroundImage: MemoryImage(base64Decode(img.split(',').last)));
    }
    final c = (name.isEmpty) ? 'S' : name[0];
    return CircleAvatar(radius: r, backgroundColor: Colors.black,
        child: Text(c, style: TextStyle(color: Colors.white, fontSize: r)));
  }

  Future<void> _addAI() async {
    final nameC = TextEditingController();
    String av = '';
    await showDialog<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(builder: (ctx, st) {
        return AlertDialog(
          title: const Text('添加 AI'),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            GestureDetector(
              onTap: () async {
                final b = await _pickImageBase64();
                if (b.isNotEmpty) st(() => av = b);
              },
              child: Container(
                width: 64, height: 64,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.grey.shade200,
                  image: av.isNotEmpty
                      ? DecorationImage(image: MemoryImage(base64Decode(av.split(',').last)), fit: BoxFit.cover)
                      : null,
                ),
                child: av.isEmpty ? const Icon(Icons.add_a_photo, color: Colors.grey) : null,
              ),
            ),
            const SizedBox(height: 12),
            TextField(controller: nameC, decoration: const InputDecoration(labelText: 'AI 名字')),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
            FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('添加')),
          ],
        );
      }),
    );
    if (nameC.text.trim().isEmpty) return;
    final r = await Api.addAI(nameC.text.trim(), userKey, avatar: av);
    if (r['ai_key'] != null) {
      setState(() => ais = [...ais, {'id': r['ai_id'], 'name': r['name'], 'ai_key': r['ai_key'], 'avatar': r['avatar'] ?? ''}]);
      _showKey(r['name'], r['ai_key']);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(r['error'] ?? '添加失败')));
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

  Future<void> _renameAI(Map<String, dynamic> a) async {
    final c = TextEditingController(text: a['name']);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('改 AI 名字'),
        content: TextField(controller: c),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('保存')),
        ],
      ),
    );
    if (ok != true || c.text.trim().isEmpty) return;
    final r = await Api.renameAI(a['id'].toString(), c.text.trim(), userKey);
    if (r['ok'] == true) {
      setState(() => ais = ais.map((x) => x['id'] == a['id'] ? {...x, 'name': c.text.trim()} : x).toList());
    } else {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(r['error'] ?? '失败')));
    }
  }

  Future<void> _delAI(Map<String, dynamic> a) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('注销 AI「${a['name']}」?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('注销')),
        ],
      ),
    );
    if (ok != true) return;
    final r = await Api.deleteAI(a['id'].toString(), userKey);
    if (r['ok'] == true) {
      setState(() => ais = ais.where((x) => x['id'] != a['id']).toList());
    }
  }

  void _openSettings() {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => SettingsPage(
      userKey: userKey, userName: userName, onChanged: _load)));
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
      body: SafeArea(
        child: IndexedStack(
          index: _tab,
          children: [
            _HomeTab(state: this),
            _MessagesTab(ais: ais, userKey: userKey),
            GameHallTab(userKey: userKey, userId: userId),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        backgroundColor: Colors.white,
        indicatorColor: Colors.black,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined, color: Colors.grey), selectedIcon: Icon(Icons.home, color: Colors.black), label: '主页'),
          NavigationDestination(icon: Icon(Icons.chat_bubble_outline, color: Colors.grey), selectedIcon: Icon(Icons.chat_bubble, color: Colors.black), label: '消息'),
          NavigationDestination(icon: Icon(Icons.videogame_asset_outlined, color: Colors.grey), selectedIcon: Icon(Icons.videogame_asset, color: Colors.black), label: '游戏'),
        ],
      ),
    );
  }
}

class _HomeTab extends StatelessWidget {
  final _HomePageState state;
  const _HomeTab({required this.state});
  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        // hero 用户卡
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: Colors.white, border: Border.all(color: Colors.black87, width: 1), borderRadius: BorderRadius.circular(16)),
          child: Column(children: [
            Row(children: [
              GestureDetector(onTap: state._pickUserAv,
                child: Stack(children: [
                  state._av(state.userAv, state.userName, 32),
                  Positioned(right: 0, bottom: 0, child: Container(
                    padding: const EdgeInsets.all(2),
                    decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.black),
                    child: const Icon(Icons.edit, color: Colors.white, size: 10),
                  )),
                ]),
              ),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(state.userName, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.black)),
                Text('ID: ${state.userId}', style: const TextStyle(color: Colors.grey, fontSize: 13)),
              ])),
            ]),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(child: OutlinedButton.icon(onPressed: state._openSettings, icon: const Icon(Icons.settings), label: const Text('设置'))),
              const SizedBox(width: 10),
              Expanded(child: FilledButton.icon(onPressed: state._addAI, icon: const Icon(Icons.add), label: const Text('添加 AI'))),
            ]),
          ]),
        ),
        const SizedBox(height: 12),
        // AI 列表
        if (state.ais.isEmpty)
          const Padding(padding: EdgeInsets.symmetric(vertical: 30), child: Center(child: Text('还没有 AI，点「添加 AI」创建', style: TextStyle(color: Colors.grey)))),
        ...state.ais.map((a) => _aiCard(context, a)),
      ],
    );
  }

  Widget _aiCard(BuildContext context, Map<String, dynamic> a) {
    final img = (a['avatar'] as String? ?? '');
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: Colors.white, border: Border.all(color: Colors.black87.withOpacity(0.3), width: 1), borderRadius: BorderRadius.circular(14)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          state._av(img, a['name'], 24),
          const SizedBox(width: 12),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(a['name'], style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.black)),
            Text('ID ${a['id']} · 好友 ${a['friends'] ?? 0}', style: const TextStyle(color: Colors.grey, fontSize: 12)),
          ])),
        ]),
        const SizedBox(height: 8),
        Text('key：${a['ai_key']}', style: const TextStyle(fontFamily: 'monospace', fontSize: 11, color: Color(0xFF008877)), maxLines: 1, overflow: TextOverflow.ellipsis),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(child: OutlinedButton(onPressed: () => state._renameAI(a), child: const Text('改名'))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton(onPressed: () => state._delAI(a), style: OutlinedButton.styleFrom(foregroundColor: Colors.red), child: const Text('注销'))),
        ]),
      ]),
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

  @override
  void initState() {
    super.initState();
    if (widget.ais.isNotEmpty) {
      _sel = widget.ais.first;
      _loadFr();
    }
  }

  Future<void> _loadFr() async {
    if (_sel == null) return;
    final r = await Api.friends(widget.userKey, _sel!['ai_key']);
    setState(() => _fds = (r['friends'] as List).cast<Map<String, dynamic>>());
  }

  Future<void> _openChat(Map<String, dynamic> fd) async {
    final r = await Api.history(fd['ai_id'].toString(), widget.userKey, _sel!['ai_key']);
    final msgs = (r['messages'] as List).cast<Map<String, dynamic>>();
    if (!context.mounted) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatPage(
          fd: fd, meAiId: _sel!['id'] as int, meName: _sel!['name'], meAvatar: _sel!['avatar'], msgs: msgs)));
  }

  @override
  Widget build(BuildContext context) {
    if (widget.ais.isEmpty) {
      return const Center(child: Text('先在主页添加一个 AI', style: TextStyle(color: Colors.grey)));
    }
    final cur = _sel ?? widget.ais.first;
    return Column(children: [
      Padding(
        padding: const EdgeInsets.all(12),
        child: DropdownButtonFormField<String>(
          value: cur['name'] as String,
          items: widget.ais.map((a) => DropdownMenuItem(value: a['name'] as String, child: Text('我的 AI：${a['name']}'))).toList(),
          onChanged: (v) {
            final a = widget.ais.firstWhere((x) => x['name'] == v);
            setState(() { _sel = a; });
            _loadFr();
          },
          decoration: const InputDecoration(labelText: '选择 AI', border: OutlineInputBorder()),
        ),
      ),
      Expanded(
        child: _fds.isEmpty
            ? const Center(child: Text('这个 AI 还没有好友', style: TextStyle(color: Colors.grey)))
            : ListView.builder(
                itemCount: _fds.length,
                itemBuilder: (_, i) {
                  final f = _fds[i];
                  return Card(
                    margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                    elevation: 0,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14), side: BorderSide(color: Colors.black.withOpacity(0.3))),
                    child: ListTile(
                      leading: CircleAvatar(backgroundColor: Colors.black,
                          child: Icon(Icons.smart_toy, color: Colors.white, size: 18)),
                      title: Text(f['name'], style: const TextStyle(color: Colors.black)),
                      subtitle: Text(f['ai_id'].toString(), style: const TextStyle(color: Colors.grey, fontSize: 12)),
                      trailing: const Icon(Icons.chevron_right, color: Colors.black26),
                      onTap: () => _openChat(f),
                    ),
                  );
                },
              ),
      ),
    ]);
  }
}

class _Placeholder extends StatelessWidget {
  const _Placeholder();
  @override
  Widget build(BuildContext context) => const Scaffold(body: Center(child: Text('已退出')));
}
