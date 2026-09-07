import 'dart:async';
import 'package:flutter/material.dart';
import 'api.dart';

class SpyRoomPage extends StatefulWidget {
  final String roomId, userKey, userId;
  const SpyRoomPage({super.key, required this.roomId, required this.userKey, required this.userId});
  @override
  State<SpyRoomPage> createState() => _SpyRoomPageState();
}

class _SpyRoomPageState extends State<SpyRoomPage> {
  Map<String, dynamic>? _room;
  Map<String, dynamic>? _card;
  Timer? _t;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _refresh();
    _t = Timer.periodic(const Duration(seconds: 3), (_) => _refresh());
  }

  @override
  void dispose() { _t?.cancel(); super.dispose(); }

  Future<void> _refresh() async {
    final r = await Api.roomStatus(widget.roomId, widget.userKey);
    if (r['room'] != null && mounted) setState(() => _room = r['room']);
    if (r['room']?['status'] == 'playing' && mounted) {
      final cr = await Api.gameMyCard(widget.roomId, widget.userKey);
      if (cr['card'] != null && mounted) setState(() => _card = cr);
    }
  }

  Future<void> _start() async {
    setState(() => _busy = true);
    final r = await Api.gameStart(widget.roomId, widget.userKey);
    setState(() => _busy = false);
    if (r['error'] != null) { _toast(r['error']); } else { await _refresh(); }
  }

  Future<void> _speak() async {
    final c = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('描述我的词'),
        content: TextField(controller: c, decoration: const InputDecoration(hintText: '说一句，别把词说破')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('发送')),
        ],
      ),
    );
    if (ok != true) return;
    await Api.gameSpeak(widget.roomId, c.text.trim(), widget.userKey);
    _refresh();
  }

  Future<void> _vote(Map<String, dynamic> p) async {
    final isAi = p['is_ai'] == true;
    final target = isAi ? (p['ai_id']?.toString()) : (p['uid']?.toString());
    if (target == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('投票淘汰 ${p['name']}?'),
        content: const Text('确认投给这个人吗'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('投票')),
        ],
      ),
    );
    if (ok != true) return;
    final r = await Api.gameVote(widget.roomId, target, widget.userKey);
    _toast(r['result'] ?? r['error'] ?? '已投票');
    _refresh();
  }

  Future<void> _reveal() async {
    final r = await Api.gameReveal(widget.roomId, widget.userKey);
    final players = (r['players'] as List? ?? []).cast<Map<String, dynamic>>();
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('本局结果：${r['result'] ?? '?'}'),
        content: SizedBox(
          width: 320,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('平民词：${r['civil']}   卧底词：${r['spy']}'),
              const Divider(),
              ...players.map((p) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Text('${p['name']}：${p['role']}（${p['card']}）${p['alive'] == true ? '' : '  [出局]'}'),
                  )),
            ],
          ),
        ),
        actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('好'))],
      ),
    );
  }

  void _toast(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    final room = _room;
    if (room == null) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    final status = (room['status'] ?? 'waiting').toString();
    final players = (room['players'] as List? ?? []).cast<Map<String, dynamic>>();
    final descs = (room['descs'] as List? ?? []).cast<Map<String, dynamic>>();
    final isHost = players.any((p) => p['uid']?.toString() == widget.userId && p['is_ai'] != true && p['host'] == true);

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(room['name'], style: const TextStyle(fontSize: 16)),
            Text('ID ${room['id']} · 谁是卧底',
                style: const TextStyle(fontSize: 12, color: Colors.grey)),
          ],
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          _statusBar(status, room, descs),
          _cardBox(status, _card),
          const SizedBox(height: 8),
          _seats(players, status),
          const SizedBox(height: 8),
          _descs(descs),
          const SizedBox(height: 8),
          _actions(status, isHost, descs),
        ],
      ),
    );
  }

  Widget _statusBar(String status, Map room, List descs) {
    String txt;
    if (status == 'waiting') txt = '等待玩家加入…';
    else if (status == 'playing') txt = '第 ${room['round']} 轮 · 描述阶段';
    else txt = '本局结束：${room['result'] ?? '?'}';
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: Colors.black, borderRadius: BorderRadius.circular(10)),
      child: Text(txt, style: const TextStyle(color: Colors.white, fontSize: 14)),
    );
  }

  Widget _cardBox(String status, Map? card) {
    Widget inner;
    if (card == null) {
      inner = const Text('游戏开始后可看到我的词', style: TextStyle(color: Colors.grey));
    } else {
      inner = Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text('我是 ${card['role']}',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.black)),
          const SizedBox(width: 16),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
            decoration: BoxDecoration(color: Colors.black, borderRadius: BorderRadius.circular(20)),
            child: Text('词：${card['card']}', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
        ],
      );
    }
    return Container(
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: Colors.grey.shade100,
        borderRadius: BorderRadius.circular(10),
      ),
      child: inner,
    );
  }

  Widget _seats(List players, String status) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(border: Border.all(color: Colors.grey.shade300), borderRadius: BorderRadius.circular(10)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('座位', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: players.map((p) {
              final canVote = status == 'playing' && p['alive'] == true && (p['is_ai'] != true || p['uid']?.toString() != widget.userId) && (p['is_ai'] == false ? p['uid']?.toString() != widget.userId : true);
              return InkWell(
                onTap: canVote ? () => _vote(p) : (status == 'playing' ? null : null),
                borderRadius: BorderRadius.circular(20),
                child: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.grey.shade200),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Column(
                    children: [
                      CircleAvatar(
                        radius: 22,
                        backgroundColor: Colors.black,
                        child: Icon(p['is_ai'] == true ? Icons.smart_toy : Icons.person, color: Colors.white),
                      ),
                      const SizedBox(height: 4),
                      Text(p['name'], style: const TextStyle(fontSize: 12)),
                      Text(
                        (p['host'] == true ? '房主 ' : '') + (p['alive'] == true ? '' : '出局'),
                        style: TextStyle(fontSize: 10, color: p['alive'] == true ? Colors.grey : Colors.red),
                      ),
                    ],
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  Widget _descs(List descs) {
    if (descs.isEmpty) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(color: Colors.grey.shade50, borderRadius: BorderRadius.circular(10)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('描述', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          ...descs.map((d) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Text('${d['name']}：${d['text']}', style: const TextStyle(fontSize: 13)),
              )),
        ],
      ),
    );
  }

  Widget _actions(String status, bool isHost, List descs) {
    if (status == 'waiting') {
      return Center(
        child: isHost
            ? FilledButton.icon(onPressed: _busy ? null : _start, icon: const Icon(Icons.play_arrow), label: const Text('开始游戏'))
            : const Text('等待房主开始…', style: TextStyle(color: Colors.grey)),
      );
    }
    if (status == 'ended') {
      return Row(
        children: [
          Expanded(child: OutlinedButton.icon(onPressed: _reveal, icon: const Icon(Icons.receipt), label: const Text('查看结果'))),
          const SizedBox(width: 10),
          Expanded(child: FilledButton(onPressed: () => Navigator.pop(context), child: const Text('返回大厅'))),
        ],
      );
    }
    return Center(
      child: FilledButton.icon(onPressed: _speak, icon: const Icon(Icons.chat_bubble_outline), label: const Text('描述我的词 / 投票')),
    );
  }
}
