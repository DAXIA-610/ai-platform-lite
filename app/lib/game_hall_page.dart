import 'package:flutter/material.dart';
import 'api.dart';
import 'spy_room_page.dart';
import 'truth_room_page.dart';

class GameHallTab extends StatefulWidget {
  final String userKey;
  final String userId;
  const GameHallTab({super.key, required this.userKey, required this.userId});
  @override
  State<GameHallTab> createState() => _GameHallTabState();
}

class _GameHallTabState extends State<GameHallTab> {
  final List<Map<String, dynamic>> _games = [
    {
      'id': 'spy',
      'name': '谁是卧底',
      'icon': Icons.visibility,
      'rule': '每人一个词（多数平民、少数卧底）。轮流描述自己的词（不能说破），每轮投票淘汰一个最像卧底的人。卧底被揪出→平民胜；卧底活到最后→卧底胜。',
    },
    {
      'id': 'truth',
      'name': '真心话大冒险',
      'icon': Icons.casino,
      'rule': '全员摇骰子，点数最大=赢家、最小=输家。输家选真心话或大冒险，赢家出题，输家回答/执行。',
    },
  ];
  Map<String, dynamic>? _room;
  bool _busy = false;

  Future<void> _create() async {
    final nameC = TextEditingController();
    int maxP = 6;
    String game = 'spy';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, st) => AlertDialog(
          title: const Text('创建房间'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(controller: nameC, decoration: const InputDecoration(labelText: '房间名')),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: game,
                items: _games
                    .map((x) => DropdownMenuItem<String>(value: x['id'] as String, child: Text(x['name'] as String)))
                    .toList(),
                onChanged: (v) { if (v != null) { game = v; st(() {}); } },
                decoration: const InputDecoration(labelText: '游戏'),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<int>(
                value: maxP,
                items: [3, 4, 5, 6]
                    .map((x) => DropdownMenuItem(value: x, child: Text('$x 人')))
                    .toList(),
                onChanged: (v) { if (v != null) { maxP = v; st(() {}); } },
                decoration: const InputDecoration(labelText: '房间人数'),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('创建')),
          ],
        ),
      ),
    );
    if (ok != true) return;
    setState(() => _busy = true);
    final r = await Api.roomCreate(nameC.text.trim(), game, maxP, widget.userKey);
    setState(() => _busy = false);
    if (r['room'] == null) { _toast(r['error'] ?? '创建失败'); return; }
    setState(() => _room = r['room']);
    _enterRoom();
  }

  Future<void> _join() async {
    final c = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('加入房间'),
        content: TextField(controller: c, decoration: const InputDecoration(labelText: '房间ID')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('加入')),
        ],
      ),
    );
    if (ok != true) return;
    final r = await Api.roomJoin(c.text.trim(), widget.userKey);
    if (r['room'] == null) { _toast(r['error'] ?? '加入失败'); return; }
    setState(() => _room = r['room']);
    _enterRoom();
  }

  void _enterRoom() {
    final rid = _room?['id'];
    if (rid == null) return;
    final game = _room?['game'] ?? 'spy';
    final Widget page = game == 'truth'
        ? TruthRoomPage(roomId: rid, userKey: widget.userKey, userId: widget.userId)
        : SpyRoomPage(
            roomId: rid,
            userKey: widget.userKey,
            userId: widget.userId,
          );
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => page)).then((_) async {
      if (!mounted) return;
      final r = await Api.roomStatus(rid, widget.userKey);
      if (r['room'] != null) { setState(() => _room = r['room']); }
      else { setState(() => _room = null); }
    });
  }

  void _toast(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Future<void> _onRoomLongPress() async {
    final isHost = (_room?['players'] as List? ?? [])
            .cast<Map>()
            .any((p) => p['host'] == true);
    final action = isHost ? '关闭房间' : '退出房间';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(action),
        content: Text(isHost ? '关闭后该房间解散' : '退出这个房间'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(action)),
        ],
      ),
    );
    if (ok != true) return;
    final r = isHost
        ? await Api.roomClose(_room!['id'], widget.userKey)
        : await Api.roomLeave(_room!['id'], widget.userKey);
    if (r['ok'] == true) { setState(() => _room = null); _toast('$action成功'); }
    else { _toast(r['error'] ?? '失败'); }
  }

  void _showRule(Map<String, dynamic> g) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: BorderSide(color: Colors.black.withOpacity(0.3))),
        title: Text(g['name'], style: const TextStyle(color: Colors.black)),
        content: Text(g['rule'], style: const TextStyle(color: Colors.black)),
        actions: [
          FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('知道了')),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // 上半：房间区
        Container(
          padding: const EdgeInsets.fromLTRB(12, 14, 12, 12),
          color: Colors.grey.shade100,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  FilledButton.icon(
                    onPressed: _busy ? null : _create,
                    icon: const Icon(Icons.add),
                    label: const Text('创建房间'),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _join,
                      icon: const Icon(Icons.key),
                      label: const Text('输邀请码加入'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              if (_room == null)
                Padding(
                  padding: const EdgeInsets.all(8),
                  child: Text('还没有房间，点「创建房间」或输邀请码', style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
                )
              else
                _roomCard(),
            ],
          ),
        ),
        // 下半：游戏卡片
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(12),
            children: _games.map((g) => _gameCard(g)).toList(),
          ),
        ),
      ],
    );
  }

  Widget _roomCard() {
    final st = _room!;
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: Colors.black87, width: 1),
        borderRadius: BorderRadius.circular(12),
      ),
      child: InkWell(
        onTap: _enterRoom,
        onLongPress: _onRoomLongPress,
        child: Container(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('🎮 ${st['name']}',
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              const SizedBox(height: 6),
              Text('房间ID：${st['id']}  状态：${st['status']}',
                  style: TextStyle(color: Colors.grey.shade700, fontSize: 13)),
              Text('人数：${(st['players'] as List).length}/${st['max_players']}',
                  style: TextStyle(color: Colors.grey.shade700, fontSize: 13)),
              const SizedBox(height: 6),
              Text('点卡片进入房间  ·  长按可关闭/退出',
                  style: TextStyle(color: Colors.grey.shade400, fontSize: 12)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _gameCard(Map<String, dynamic> g) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(color: Colors.white, border: Border.all(color: Colors.black87, width: 1), borderRadius: BorderRadius.circular(12)),
      child: ListTile(
        title: Text(g['name'], style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text(g['rule'], maxLines: 2, overflow: TextOverflow.ellipsis),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => _showRule(g),
      ),
    );
  }
}
