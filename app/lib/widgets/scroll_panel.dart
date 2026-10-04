import 'package:flutter/material.dart';

import '../providers/truth_room_provider.dart';
import 'room_theme.dart';

/// 中央书卷（牌桌）。
///
/// **只按 `phase` 渲染**，不自己发明状态：
///   waiting / roll / choose / question / answer / result
/// `phase` 不变时书卷内容就不换，换的时候走 AnimatedSwitcher 淡一下。
class ScrollPanel extends StatelessWidget {
  const ScrollPanel({super.key, required this.p});

  final TruthRoomProvider p;

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 260),
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeIn,
      child: Container(
        // key 绑在 phase 上，阶段一变就换内容
        key: ValueKey<String>(p.phase),
        decoration: RoomTheme.paperBox(radius: 16, glowing: p.phase == 'choose'),
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
        child: SingleChildScrollView(
          child: _body(context),
        ),
      ),
    );
  }

  Widget _body(BuildContext context) {
    switch (p.phase) {
      case 'roll':
        return _roll(context);
      case 'choose':
        return _choose(context);
      case 'question':
        return _question(context);
      case 'answer':
        return _answer(context);
      case 'result':
        return _result(context);
      case 'waiting':
      default:
        return _waiting(context);
    }
  }

  // ==================== waiting ====================
  // 后端 phase 是 waiting（还没开局）。status 这时也是 waiting。

  Widget _waiting(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _scrollHead('未 开 局'),
        const SizedBox(height: 6),
        const Text('等待房主开启游戏', style: RoomTheme.title),
        const SizedBox(height: 10),
        _roomCode(),
        const SizedBox(height: 8),
        Text('${p.players.length}/${p.maxPlayers} 人已入席', style: RoomTheme.hint),
        const SizedBox(height: 12),
        if (p.isHost)
          _btn('开始游戏', icon: Icons.play_arrow_rounded, onTap: p.busy ? null : () => p.act('start'))
        else
          const Text('等房主开始…', style: RoomTheme.hint),
      ],
    );
  }

  Widget _roomCode() => Column(
        children: [
          const Text('房间号', style: RoomTheme.hint),
          const SizedBox(height: 2),
          Text(
            p.roomId,
            style: const TextStyle(
              color: RoomTheme.goldDeep,
              fontSize: 22,
              fontWeight: FontWeight.w800,
              letterSpacing: 4,
            ),
          ),
        ],
      );

  // ==================== roll ====================

  Widget _roll(BuildContext context) {
    final mine = p.myPoint;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _scrollHead('第 ${p.round} 局 · 摇 骰 子'),
        const SizedBox(height: 8),
        _dice(mine),
        const SizedBox(height: 8),
        mine == null
            ? _btn('摇骰子', icon: Icons.casino_outlined, onTap: p.busy ? null : () => p.act('roll'))
            : Text('你摇到 $mine 点，等其他人…', style: RoomTheme.hint),
        if (p.countdown > 0 && mine == null) ...[
          const SizedBox(height: 6),
          Text('${p.countdown} 秒后自动摇', style: RoomTheme.hint),
        ],
      ],
    );
  }

  Widget _dice(int? mine) => Container(
        width: 74,
        height: 74,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color.fromRGBO(59, 42, 24, 0.28), width: 1.4),
          boxShadow: const [
            BoxShadow(color: Color.fromRGBO(59, 42, 24, 0.25), blurRadius: 10, offset: Offset(0, 3)),
          ],
        ),
        child: Text(
          mine == null ? '?' : '$mine',
          style: TextStyle(
            fontSize: mine == null ? 34 : 40,
            fontWeight: FontWeight.w800,
            color: mine == null ? RoomTheme.inkSoft : RoomTheme.ink,
          ),
        ),
      );

  // ==================== choose ====================

  Widget _choose(BuildContext context) {
    final w = p.winnerPlayer?['name'] ?? '赢家';
    final l = p.loserPlayer?['name'] ?? '输家';
    final picked = p.loserChoice;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _scrollHead('第 ${p.round} 局 · 选 择'),
        const SizedBox(height: 8),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            _tagLine('赢家', '$w', RoomTheme.win),
            _tagLine('输家', '$l', RoomTheme.lose),
          ],
        ),
        const SizedBox(height: 10),
        if (p.isLoser && picked == null) ...[
          const Text('选一个', style: RoomTheme.title),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: _btn('真心话', bg: RoomTheme.truthRed, onTap: p.busy ? null : () => p.act('choose', choice: '0')),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _btn('大冒险', bg: RoomTheme.dareBlue, onTap: p.busy ? null : () => p.act('choose', choice: '1')),
              ),
            ],
          ),
        ] else
          Text(
            picked == null ? '等 $l 选真心话 / 大冒险…' : '已选：${picked == 'dare' ? '大冒险' : '真心话'}',
            style: RoomTheme.hint,
          ),
        if (p.countdown > 0 && picked == null) ...[
          const SizedBox(height: 6),
          Text('${p.countdown} 秒后自动选', style: RoomTheme.hint),
        ],
      ],
    );
  }

  // ==================== question ====================

  Widget _question(BuildContext context) {
    final w = p.winnerPlayer?['name'] ?? '赢家';
    final q = p.question;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _scrollHead('第 ${p.round} 局 · 出 题'),
        const SizedBox(height: 6),
        Text('由 $w 出题', style: RoomTheme.hint),
        const SizedBox(height: 8),
        _questionBox(q),
        const SizedBox(height: 6),
        Text(
          p.taskId == null ? '待定' : '题库 · ${p.taskId}',
          style: RoomTheme.hint,
        ),
        const SizedBox(height: 8),
        if (p.isWinner) ...[
          Row(
            children: [
              Expanded(
                child: _btn('换一题', bg: RoomTheme.dareBlue, onTap: p.busy ? null : () => p.act('redraw')),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _btn('就用这题', onTap: p.busy || q == null ? null : () => p.act('use')),
              ),
            ],
          ),
          const SizedBox(height: 6),
          TextButton(
            onPressed: p.busy
                ? null
                : () => _ask(context, title: '自己出题', hint: '写一句你想问的', action: 'input'),
            child: const Text('或者我自己出', style: TextStyle(color: RoomTheme.inkSoft, fontSize: 13)),
          ),
        ] else
          Text('等 $w 定题…', style: RoomTheme.hint),
        if (p.countdown > 0) ...[
          const SizedBox(height: 4),
          Text('${p.countdown} 秒', style: RoomTheme.hint),
        ],
      ],
    );
  }

  Widget _questionBox(String? q) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color.fromRGBO(255, 255, 255, 0.62),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: const Color.fromRGBO(59, 42, 24, 0.18)),
        ),
        child: Text(
          q == null || q.isEmpty ? '（还没有题）' : q,
          textAlign: TextAlign.center,
          style: const TextStyle(color: RoomTheme.ink, fontSize: 15, height: 1.5, fontWeight: FontWeight.w600),
        ),
      );

  // ==================== answer ====================

  Widget _answer(BuildContext context) {
    final l = p.loserPlayer?['name'] ?? '输家';
    final isDare = p.loserChoice == 'dare';
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _scrollHead(isDare ? '第 ${p.round} 局 · 大 冒 险' : '第 ${p.round} 局 · 真 心 话'),
        const SizedBox(height: 8),
        _questionBox(p.question),
        const SizedBox(height: 10),
        if (p.isLoser)
          isDare
              ? Row(
                  children: [
                    Expanded(
                      child: _btn('稍后执行', bg: RoomTheme.dareBlue, onTap: p.busy ? null : () => p.act('do', choice: '1')),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _btn('我已执行', onTap: p.busy ? null : () => p.act('do', choice: '0')),
                    ),
                  ],
                )
              : _btn('写回答', icon: Icons.edit_outlined, onTap: p.busy ? null : () => _ask(context, title: '真心话', hint: '说说吧', action: 'input'))
        else
          Text('等 $l ${isDare ? '执行' : '回答'}…', style: RoomTheme.hint),
        if (p.countdown > 0) ...[
          const SizedBox(height: 6),
          Text('${p.countdown} 秒', style: RoomTheme.hint),
        ],
      ],
    );
  }

  // ==================== result ====================

  Widget _result(BuildContext context) {
    final w = p.winnerPlayer?['name'] ?? '赢家';
    final l = p.loserPlayer?['name'] ?? '输家';
    final isDare = p.loserChoice == 'dare';
    final done = p.dare == 'done';
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _scrollHead('第 ${p.round} 局 · 结 果'),
        const SizedBox(height: 8),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            _tagLine('赢家', '$w', RoomTheme.win),
            _tagLine('输家', '$l', RoomTheme.lose),
          ],
        ),
        const SizedBox(height: 10),
        if (p.question != null) ...[
          _kv(isDare ? '任务' : '题目', p.question!),
          const SizedBox(height: 6),
        ],
        if (isDare)
          _kv('执行', p.dare == null ? '未确认' : (done ? '已执行' : '稍后执行'))
        else
          _kv('回答', (p.answer == null || p.answer!.isEmpty) ? '（没有作答）' : p.answer!),
        const SizedBox(height: 12),
        if (p.isHost)
          _btn('下一局', icon: Icons.replay_rounded, onTap: p.busy ? null : () => p.act('start'))
        else
          const Text('等房主开下一局…', style: RoomTheme.hint),
      ],
    );
  }

  // ==================== 小零件 ====================

  Widget _scrollHead(String text) => Column(
        children: [
          Text(
            text,
            style: const TextStyle(
              color: RoomTheme.goldDeep,
              fontSize: 12,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.2,
            ),
          ),
          const SizedBox(height: 4),
          Container(height: 1, color: const Color.fromRGBO(140, 111, 20, 0.28)),
        ],
      );

  Widget _tagLine(String k, String v, Color c) => Column(
        children: [
          Text(k, style: TextStyle(color: c, fontSize: 11, fontWeight: FontWeight.w700)),
          const SizedBox(height: 2),
          SizedBox(
            width: 78,
            child: Text(
              v,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: const TextStyle(color: RoomTheme.ink, fontSize: 13, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      );

  Widget _kv(String k, String v) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 40,
            child: Text(k, style: RoomTheme.hint),
          ),
          Expanded(
            child: Text(v, style: const TextStyle(color: RoomTheme.ink, fontSize: 13.5, height: 1.45)),
          ),
        ],
      );

  Widget _btn(
    String label, {
    required VoidCallback? onTap,
    Color bg = RoomTheme.goldDeep,
    IconData? icon,
  }) {
    final disabled = onTap == null;
    return Material(
      color: disabled ? const Color(0xFFB4A488) : bg,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 10),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) Icon(icon, size: 16, color: Colors.white),
              if (icon != null) const SizedBox(width: 5),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white, fontSize: 13.5, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// 弹个输入框，确认后把文字发出去
  Future<void> _ask(
    BuildContext context, {
    required String title,
    required String hint,
    required String action,
  }) async {
    final c = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: RoomTheme.paper,
        title: Text(title, style: RoomTheme.title),
        content: TextField(
          controller: c,
          autofocus: true,
          maxLines: 3,
          minLines: 1,
          decoration: InputDecoration(hintText: hint, hintStyle: RoomTheme.hint),
          style: RoomTheme.body,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: RoomTheme.goldDeep),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('发送'),
          ),
        ],
      ),
    );
    final text = c.text.trim();
    if (ok == true && text.isNotEmpty) {
      await p.act(action, text: text);
    }
  }
}
