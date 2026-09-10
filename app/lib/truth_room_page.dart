import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';
import 'api.dart';

class TruthRoomPage extends StatefulWidget {
  final String roomId, userKey, userId;
  const TruthRoomPage({super.key, required this.roomId, required this.userKey, required this.userId});
  @override
  State<TruthRoomPage> createState() => _TruthRoomPageState();
}

class _TruthRoomPageState extends State<TruthRoomPage> {
  Map<String, dynamic>? _room;
  Timer? _t;
  Timer? _anim;
  bool _rolling = false;
  bool _busy = false;
  int _miss = 0;
  int? _animPoint;

  @override
  void initState() { super.initState(); _refresh(); _t = Timer.periodic(const Duration(seconds: 2), (_) => _refresh()); }
  @override
  void dispose() { _t?.cancel(); _anim?.cancel(); super.dispose(); }

  Future<void> _refresh() async {
    final r = await Api.roomStatus(widget.roomId, widget.userKey);
    if (!mounted) return;
    if (r['room'] != null) {
      _miss = 0;
      setState(() => _room = r['room']);
    } else {
      _miss++;
      if (_miss >= 3) {
        _t?.cancel();
        _toast('房间已解散');
        Navigator.of(context).maybePop();
      }
    }
  }

  List<Map<String, dynamic>> _players() => (_room?['players'] as List? ?? []).cast<Map<String, dynamic>>();

  Map<String, dynamic>? _me() {
    for (final p in _players()) {
      if (p['is_ai'] != true && p['uid']?.toString() == widget.userId) return p;
    }
    return null;
  }

  Widget _avOf(Map p, double r) {
    final img = p['avatar'] as String? ?? '';
    if (img.isNotEmpty && img.length > 4 && img.contains('base64')) {
      return CircleAvatar(radius: r, backgroundColor: Colors.black,
          backgroundImage: MemoryImage(base64Decode(img.split(',').last)));
    }
    final name = (p['name'] ?? 'S').toString();
    return CircleAvatar(radius: r, backgroundColor: Colors.black,
        child: Text(name.isEmpty ? 'S' : name[0], style: const TextStyle(color: Colors.white, fontSize: 16)));
  }

  bool _match(dynamic key, Map p) {
    if (key is List && key.length >= 2) {
      if (key[0] == 'a') return p['ai_id']?.toString() == key[1].toString();
      return p['uid']?.toString() == key[1].toString() && p['is_ai'] != true;
    }
    return false;
  }

  Map<String, dynamic>? _byKey(dynamic key) {
    for (final p in _players()) { if (_match(key, p)) return p; }
    return null;
  }

  int? _pointOf(Map p) {
    final rolls = _room?['rolls'];
    if (rolls is List) {
      for (final item in rolls) { if (_match(item['k'], p)) return item['v']; }
    }
    return null;
  }

  Future<void> _start() async {
    if (_busy) return;
    setState(() => _busy = true);
    final r = await Api.gameStart(widget.roomId, widget.userKey);
    if (mounted) setState(() => _busy = false);
    if (r['ok'] != true) _toast((r['error'] ?? '开始失败').toString());
    _refresh();
  }

  void _toast(String m) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));
  }

  Future<void> _rollTap() async {
    if (_rolling || _busy) return;
    setState(() { _rolling = true; _busy = true; });
    _anim?.cancel();
    _anim = Timer.periodic(const Duration(milliseconds: 90), (_) {
      setState(() => _animPoint = 1 + Random().nextInt(6));
    });
    final r = await Api.truthOp(widget.roomId, 'roll', widget.userKey);
    await Future.delayed(const Duration(milliseconds: 700));
    _anim?.cancel();
    await _refresh();
    if (mounted) setState(() { _rolling = false; _busy = false; _animPoint = null; });
    if (r['ok'] != true) _toast((r['error'] ?? '摇骰失败').toString());
  }

  Future<void> _op(String action, {int choice = -1, String text = ''}) async {
    if (_busy) return;
    setState(() => _busy = true);
    final r = await Api.truthOp(widget.roomId, action, widget.userKey,
        choice: choice >= 0 ? choice.toString() : '', text: text);
    await _refresh();
    if (mounted) setState(() => _busy = false);
    if (r['ok'] != true) _toast((r['error'] ?? '操作失败').toString());
  }

  Future<void> _input() async {
    final c = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.white,
        title: const Text('输入', style: TextStyle(color: Colors.black)),
        content: TextField(controller: c, autofocus: true, decoration: const InputDecoration(hintText: '输入内容')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('确认')),
        ],
      ),
    );
    if (ok != true) return;
    await _op('input', text: c.text.trim());
  }

  @override
  Widget build(BuildContext context) {
    final room = _room;
    if (room == null) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    final players = _players();
    final me = _me();
    final phase = (room['phase'] ?? 'waiting').toString();
    final round = room['round'] ?? 1;
    final isHost = players.any((p) => p['host'] == true && p['is_ai'] != true && p['uid']?.toString() == widget.userId);
    final isWinner = me != null && _match(room['winner'], me);
    final isLoser = me != null && _match(room['loser'], me);
    final myPoint = me != null ? _pointOf(me) : null;
    final lc = room['loser_choice'];
    final q = room['question'];
    final a = room['answer'];
    final dare = room['dare'];
    final die = _rolling ? (_animPoint ?? 1) : (myPoint ?? 0);

    return Scaffold(
      backgroundColor: const Color(0xFFF2F2F2),
      appBar: AppBar(
        backgroundColor: Colors.white, foregroundColor: Colors.black,
        title: Text('${room['name']} · 真心话', style: const TextStyle(fontSize: 16)),
        actions: [ if (isHost) IconButton(icon: const Icon(Icons.play_arrow), color: Colors.black, tooltip: '开始/下一局', onPressed: _start) ],
      ),
      body: SafeArea(child: Column(children: [
        // 座位席
        Container(
          width: double.infinity, padding: const EdgeInsets.all(12),
          child: Wrap(spacing: 10, runSpacing: 10, children: players.map((p) {
            final win = _match(room['winner'], p);
            final lose = _match(room['loser'], p);
            final pt = _pointOf(p);
            final host = p['host'] == true;
            return Container(
              width: 66,
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: host ? Colors.black : Colors.black12, width: host ? 1.4 : 1),
                boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 4, offset: Offset(0, 1))],
              ),
              child: Column(children: [
                Stack(children: [
                  _avOf(p, 20),
                  if (win) const Positioned(top: -2, left: 8, child: _tag('赢', Color(0xFF008877))),
                  if (lose) const Positioned(top: -2, left: 8, child: _tag('输', Colors.red)),
                ]),
                const SizedBox(height: 3),
                Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                  Flexible(child: Text(p['name'] ?? '', style: const TextStyle(fontSize: 11), overflow: TextOverflow.ellipsis)),
                  if (host) const Text(' 👑', style: TextStyle(fontSize: 9)),
                ]),
                Text(pt == null ? '·' : '$pt', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold)),
              ]));
          }).toList()),
        ),
        // 弹幕卡
        Padding(padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4), child: _banner(phase, lc, q, a, dare)),
        // 大骰子
        Expanded(child: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
          Container(
            width: 130, height: 130,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(26),
              border: Border.all(color: Colors.black.withOpacity(0.15), width: 1.2),
              boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 12, offset: Offset(0, 4))],
            ),
            child: Text(_rolling ? '🎲' : (myPoint == null ? '?' : '$die'),
                style: TextStyle(fontSize: _rolling ? 58 : 52, fontWeight: FontWeight.bold, color: Colors.black)),
          ),
          const SizedBox(height: 8),
          Text(_rolling ? '摇骰中…' : (myPoint == null ? '等待摇骰' : '我的点数'), style: const TextStyle(color: Colors.grey, fontSize: 12)),
        ]))),
        // 操作区
        Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
          child: _actions(phase, isHost, isWinner, isLoser, myPoint, lc, q, a, dare),
        ),
        Text('第 $round 局', style: const TextStyle(color: Colors.grey, fontSize: 12)),
      ])),
    );
  }

  Widget _banner(String phase, lc, q, a, dare) {
    final loserName = _byKey(_room?['loser'])?['name'] ?? '输家';
    final winnerName = _byKey(_room?['winner'])?['name'] ?? '赢家';
    String text;
    if (phase == 'waiting') {
      text = '等待房主开始，喊上朋友一起摇骰子';
    } else if (phase == 'roll') {
      text = '全员摇骰子，点数最大是赢家、最小是输家';
    } else if (phase == 'choose') {
      text = '等 $loserName 选真心话 / 大冒险…';
    } else if (phase == 'question') {
      text = lc == 'dare'
          ? '$loserName 选了大冒险，等 $winnerName 出任务…'
          : '$loserName 选了真心话，等 $winnerName 出题…';
    } else if (phase == 'answer') {
      if (q == null) {
        text = lc == 'dare' ? '等 $winnerName 出任务…' : '等 $winnerName 出题…';
      } else {
        text = (lc == 'dare' ? '任务：' : '题目：') + '$q\n请 $loserName ' + (lc == 'dare' ? '执行' : '回答');
      }
    } else {
      if (a != null) text = '回答：$a';
      else if (dare != null) text = '大冒险：$q\n$loserName ${dare == 'done' ? '已执行' : '稍后执行'}';
      else if (q != null) text = '本局结束：$q';
      else text = '本局结束';
    }
    if (text.isEmpty) return const SizedBox.shrink();
    return Container(
      width: double.infinity, padding: const EdgeInsets.all(12),
      constraints: const BoxConstraints(minHeight: 44),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.black.withOpacity(0.2)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Icon(Icons.campaign, color: Colors.black54, size: 18),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: const TextStyle(color: Colors.black, fontSize: 14))),
      ]),
    );
  }

  Widget _actions(phase, isHost, isWinner, isLoser, myPoint, lc, q, a, dare) {
    if (_busy) {
      return const Center(child: SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2)));
    }
    if (phase == 'roll') {
      return Center(child: myPoint == null
          ? FilledButton.icon(onPressed: _rollTap, style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14)), icon: const Icon(Icons.casino), label: const Text('摇骰子'))
          : const Text('已摇，等待其他玩家…', style: TextStyle(color: Colors.grey)));
    }
    if (phase == 'choose') {
      if (isLoser) return Row(children: [
        Expanded(child: FilledButton(onPressed: () => _op('choose', choice: 0), child: const Text('真心话'))),
        const SizedBox(width: 12),
        Expanded(child: OutlinedButton(onPressed: () => _op('choose', choice: 1), child: const Text('大冒险'))),
      ]);
      return const Center(child: Text('等待输家选择…', style: TextStyle(color: Colors.grey)));
    }
    if (phase == 'question') {
      if (isWinner) return Center(child: FilledButton.icon(onPressed: _input, icon: const Icon(Icons.edit), label: Text(lc == 'dare' ? '输入任务' : '输入问题')));
      return const Center(child: Text('等待赢家出题…', style: TextStyle(color: Colors.grey)));
    }
    if (phase == 'answer') {
      if (lc == 'truth') {
        if (isLoser) return Center(child: FilledButton.icon(onPressed: _input, icon: const Icon(Icons.chat), label: const Text('回答问题')));
        return const Center(child: Text('等待输家回答…', style: TextStyle(color: Colors.grey)));
      } else {
        if (isLoser) return Row(children: [
          Expanded(child: OutlinedButton(onPressed: () => _op('do', choice: 1), child: const Text('稍后执行'))),
          const SizedBox(width: 12),
          Expanded(child: FilledButton(onPressed: () => _op('do', choice: 0), child: const Text('我已执行'))),
        ]);
        return const Center(child: Text('等待输家执行…', style: TextStyle(color: Colors.grey)));
      }
    }
    if (phase == 'result') {
      final w = _byKey(_room?['winner'])?['name'] ?? '赢家';
      final l = _byKey(_room?['loser'])?['name'] ?? '输家';
      return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text('$w 赢  ·  $l 输', style: const TextStyle(color: Colors.black, fontSize: 14)),
        const SizedBox(height: 4),
        const Text('本局结束', style: TextStyle(color: Colors.black, fontWeight: FontWeight.bold, fontSize: 15)),
        if (isHost) ...[
          const SizedBox(height: 10),
          FilledButton.icon(onPressed: _start, icon: const Icon(Icons.replay), label: const Text('下一局')),
        ],
      ]));
    }
    return const SizedBox.shrink();
  }
}

class _tag extends StatelessWidget {
  final String t; final Color c;
  const _tag(this.t, this.c);
  @override
  Widget build(BuildContext c2) => Container(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
      color: c, child: Text(t, style: const TextStyle(color: Colors.white, fontSize: 9)));
}
