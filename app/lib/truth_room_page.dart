import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'providers/truth_room_provider.dart';
import 'widgets/player_avatar.dart';
import 'widgets/room_theme.dart';
import 'widgets/scroll_panel.dart';

/// 真心话大冒险 · 房间页
///
/// 布局是三层叠的：
///   底  ——  宴会厅暗色渐变（羊皮纸那套色，见 room_theme.dart）
///   中  ——  环形座位：头像按三角函数均匀排一圈，中间空出来给书卷
///   心  ——  书卷（ScrollPanel），只按后端给的 `phase` 换内容
///
/// 真人玩家在真机上操作；**AI 玩家由后端 MCP 驱动，这里只画它的状态**
/// （轮到 AI 又没动时显示“AI 思考中”），永远不给 AI 留按钮。
class TruthRoomPage extends StatefulWidget {
  const TruthRoomPage({
    super.key,
    required this.roomId,
    required this.userKey,
    required this.userId,
  });

  final String roomId;
  final String userKey;
  final String userId;

  @override
  State<TruthRoomPage> createState() => _TruthRoomPageState();
}

class _TruthRoomPageState extends State<TruthRoomPage> {
  late final TruthRoomProvider p;
  String? _shownError;

  @override
  void initState() {
    super.initState();
    p = TruthRoomProvider(
      roomId: widget.roomId,
      userKey: widget.userKey,
      userId: widget.userId,
    );
    p.addListener(_onChange);
  }

  @override
  void dispose() {
    p.removeListener(_onChange);
    p.dispose();
    super.dispose();
  }

  /// 出错弹一下；房间没了就自己退出去
  void _onChange() {
    final e = p.error;
    if (e == null || e == _shownError || !mounted) return;
    _shownError = e;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e)));
    if (e == '房间已解散') {
      Navigator.of(context).maybePop();
      return;
    }
    p.clearError();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: RoomTheme.bgBottom,
      body: ListenableBuilder(
        listenable: p,
        builder: (context, _) {
          if (p.loading && p.room == null) {
            return const Center(
              child: CircularProgressIndicator(
                valueColor: AlwaysStoppedAnimation<Color>(RoomTheme.gold),
              ),
            );
          }
          return Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [RoomTheme.bgTop, RoomTheme.bgMid, RoomTheme.bgBottom],
              ),
            ),
            child: SafeArea(
              child: Column(
                children: [
                  _topBar(),
                  Expanded(
                    child: LayoutBuilder(
                      builder: (ctx, box) => _ring(ctx, box),
                    ),
                  ),
                  _bottomBar(),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  // ==================== 顶栏 ====================

  Widget _topBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 4),
      child: Container(
        decoration: RoomTheme.barBox(),
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
        child: Row(
          children: [
            IconButton(
              icon: const Icon(Icons.arrow_back_ios_new, size: 17, color: RoomTheme.goldSoft),
              onPressed: () => Navigator.of(context).maybePop(),
            ),
            Expanded(
              child: Column(
                children: [
                  Text(
                    p.roomName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: RoomTheme.goldSoft,
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.5,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'ID ${p.roomId} · ${_phaseLabel()} · 第 ${p.round} 局',
                    style: const TextStyle(color: Color.fromRGBO(226, 201, 126, 0.62), fontSize: 11),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: Text(
                '${p.players.length}/${p.maxPlayers}',
                style: const TextStyle(color: RoomTheme.goldSoft, fontSize: 12.5, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _phaseLabel() {
    switch (p.phase) {
      case 'roll':
        return '摇骰子';
      case 'choose':
        return '选择';
      case 'question':
        return '出题';
      case 'answer':
        return '作答';
      case 'result':
        return '结果';
      default:
        return '等待开局';
    }
  }

  // ==================== 环形座位 + 中央书卷 ====================

  Widget _ring(BuildContext context, BoxConstraints c) {
    final n = p.players.length;
    final w = c.maxWidth;
    final h = c.maxHeight;
    if (n == 0) {
      return const Center(child: Text('房间里还没有人', style: RoomTheme.onDark));
    }

    // 人多就把头像缩小，不然一圈挤不开
    final av = n <= 6 ? 62.0 : (n <= 9 ? 54.0 : 46.0);
    final slotH = av + 36; // 头像 + 名字 + 状态行

    // 头像是排在一个椭圆上的：
    //   x = cx + rx·sin(a)，y = cy − ry·cos(a)，a = 2πi/n
    // 从正上方开始、顺时针一圈。rx 受屏幕宽限制，ry 可以吃满竖直空间（竖屏更高）。
    final rx = math.max(60.0, (w - av - 36) / 2);
    final ry = math.max(60.0, (h - slotH - 16) / 2);

    // 书卷先给个大小，再按“别和任何一个头像重叠”自动收缩
    var sw = math.min(w * 0.58, rx * 1.12);
    var sh = math.min(h * 0.60, ry * 1.04);
    for (var guard = 0; guard < 26; guard++) {
      var clash = false;
      for (var i = 0; i < n; i++) {
        final a = 2 * math.pi * i / n;
        final px = (rx * math.sin(a)).abs();
        final py = (ry * math.cos(a)).abs();
        // 头像在 x / y 两个方向上只要有一个出了书卷的边，就不算撞上
        final dx = (px + av / 2 + 6) - sw / 2;
        final dy = (py + slotH / 2 + 6) - sh / 2;
        if (dx < 0 && dy < 0) {
          clash = true;
          break;
        }
      }
      if (!clash) break;
      sw *= 0.95;
      sh *= 0.95;
    }
    sw = math.max(sw, 132);
    sh = math.max(sh, 168);

    final cx = w / 2;
    final cy = h / 2;

    final seats = <Widget>[];
    for (var i = 0; i < n; i++) {
      final a = 2 * math.pi * i / n;
      final x = cx + rx * math.sin(a) - av / 2 - 10;
      final y = cy - ry * math.cos(a) - slotH / 2;
      final player = p.players[i];
      seats.add(Positioned(
        left: x,
        top: y,
        width: av + 20,
        height: slotH,
        child: Center(
          child: PlayerAvatar(
            player: player,
            p: p,
            size: av,
            highlight: p.isActing(player),
          ),
        ),
      ));
    }

    return Stack(
      children: [
        Center(
          child: SizedBox(
            width: sw,
            height: sh,
            child: ScrollPanel(p: p),
          ),
        ),
        ...seats,
      ],
    );
  }

  // ==================== 底部：操作提示 + 可折叠的“我的信息” ====================

  Widget _bottomBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(10, 4, 10, 8),
      child: Container(
        decoration: RoomTheme.barBox(),
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 4),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    p.myPoint == null ? '我的点数：—' : '我的点数：${p.myPoint}',
                    style: const TextStyle(color: RoomTheme.goldSoft, fontSize: 12.5),
                  ),
                ),
                TextButton(
                  style: TextButton.styleFrom(
                    minimumSize: const Size(0, 30),
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  onPressed: p.togglePrivate,
                  child: Text(
                    p.showPrivate ? '收起 ▲' : '我的信息 ▼',
                    style: const TextStyle(color: RoomTheme.goldSoft, fontSize: 12),
                  ),
                ),
              ],
            ),
            if (p.showPrivate) _privatePanel(),
          ],
        ),
      ),
    );
  }

  Widget _privatePanel() {
    final who = p.isWinner ? '赢家' : (p.isLoser ? '输家' : '围观');
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Divider(color: const Color.fromRGBO(201, 162, 39, 0.25), height: 10),
          _kv('我的身份', who),
          _kv('本局题目', p.taskId == null ? '还没抽' : '题库 ${p.taskId}'),
          _kv('房间号', p.roomId),
          const Padding(
            padding: EdgeInsets.only(top: 4),
            child: Text(
              'AI 玩家由后端驱动，你不能替它操作。',
              style: TextStyle(color: Color.fromRGBO(226, 201, 126, 0.5), fontSize: 11),
            ),
          ),
        ],
      ),
    );
  }

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 1),
        child: Row(
          children: [
            SizedBox(
              width: 62,
              child: Text(k, style: const TextStyle(color: Color.fromRGBO(226, 201, 126, 0.6), fontSize: 11.5)),
            ),
            Expanded(
              child: Text(v, style: const TextStyle(color: RoomTheme.goldSoft, fontSize: 11.5)),
            ),
          ],
        ),
      );
}
