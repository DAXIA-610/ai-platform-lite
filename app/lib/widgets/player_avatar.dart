import 'dart:convert';

import 'package:flutter/material.dart';

import '../providers/truth_room_provider.dart';
import 'room_theme.dart';

/// 环形座位上的一个玩家头像。
///
/// 边框颜色就是身份：**金色 = 真人，蓝色 = AI**。
/// AI 轮到它动而还没动时，下面显示“AI 思考中” + 转圈——前端永远不给 AI 操作按钮。
class PlayerAvatar extends StatelessWidget {
  const PlayerAvatar({
    super.key,
    required this.player,
    required this.p,
    this.size = 60,
    this.highlight = false,
  });

  final Map<String, dynamic> player;
  final TruthRoomProvider p;

  /// 头像圆直径。人多的时候由页面调小。
  final double size;

  /// 行动中：加一圈光晕
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    final isAi = player['is_ai'] == true;
    final isMe = !isAi && '${player['uid']}' == p.userId;
    final isHost = player['host'] == true;
    final isWinner = p.isWinnerP(player);
    final isLoser = p.isLoserP(player);
    final alive = player['alive'] != false;
    final thinking = p.isAiThinking(player);
    final point = p.pointOf(player);
    final name = (player['name'] ?? '?').toString();

    final edge = isAi ? RoomTheme.aiEdge : RoomTheme.humanEdge;
    final edgeWidth = (highlight || isWinner || isLoser) ? 2.6 : 1.6;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Stack(
          clipBehavior: Clip.none,
          alignment: Alignment.center,
          children: [
            // 行动中的光晕
            if (highlight)
              Container(
                width: size + 10,
                height: size + 10,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color.fromRGBO(226, 201, 126, 0.55), width: 1.4),
                  boxShadow: const [
                    BoxShadow(color: Color.fromRGBO(226, 201, 126, 0.35), blurRadius: 14, spreadRadius: 1),
                  ],
                ),
              ),
            Opacity(
              opacity: alive ? 1 : 0.42,
              child: Container(
                width: size,
                height: size,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFF1E150D),
                  border: Border.all(color: edge, width: edgeWidth),
                ),
                child: ClipOval(child: _face(name, size)),
              ),
            ),
            // 左右角标：赢 / 输
            if (isWinner) _corner('赢', RoomTheme.win, left: true),
            if (isLoser) _corner('输', RoomTheme.lose, left: false),
            // 我 / 房主
            if (isMe)
              Positioned(
                right: -1,
                bottom: -1,
                child: _dot('我', const Color(0xFF6B5220)),
              ),
            if (isHost)
              const Positioned(right: -2, top: -2, child: Text('👑', style: TextStyle(fontSize: 12))),
          ],
        ),
        const SizedBox(height: 3),
        SizedBox(
          width: size + 20,
          child: Text(
            name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: size >= 54 ? 11.5 : 10,
              color: alive ? RoomTheme.goldSoft : const Color.fromRGBO(226, 201, 126, 0.45),
              fontWeight: isMe ? FontWeight.w700 : FontWeight.w500,
            ),
          ),
        ),
        // 状态行：思考中 > 点数 > 标签
        SizedBox(
          height: 15,
          child: thinking
              ? Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const SizedBox(
                      width: 9,
                      height: 9,
                      child: CircularProgressIndicator(
                        strokeWidth: 1.5,
                        valueColor: AlwaysStoppedAnimation<Color>(RoomTheme.thinking),
                      ),
                    ),
                    const SizedBox(width: 3),
                    Text(
                      'AI 思考中',
                      style: TextStyle(
                        fontSize: size >= 54 ? 9.5 : 8.5,
                        color: RoomTheme.thinking,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                )
              : Text(
                  point != null ? '$point 点' : (isAi ? 'AI' : (alive ? '' : '出局')),
                  style: TextStyle(
                    fontSize: size >= 54 ? 10.5 : 9.5,
                    fontWeight: point != null ? FontWeight.w700 : FontWeight.normal,
                    color: point != null ? RoomTheme.goldSoft : const Color.fromRGBO(226, 201, 126, 0.5),
                  ),
                ),
        ),
      ],
    );
  }

  /// 头像本体：有图用图，没图用名字第一个字
  Widget _face(String name, double size) {
    final img = player['avatar']?.toString() ?? '';
    if (img.length > 8 && img.contains('base64')) {
      try {
        return Image.memory(
          base64Decode(img.split(',').last),
          fit: BoxFit.cover,
          width: size,
          height: size,
          errorBuilder: (_, __, ___) => _initial(name, size),
        );
      } catch (_) {/* 图坏了就退回首字 */}
    }
    return _initial(name, size);
  }

  Widget _initial(String name, double size) => Center(
        child: Text(
          name.isEmpty ? '?' : name[0],
          style: TextStyle(
            color: RoomTheme.goldSoft,
            fontSize: size * 0.42,
            fontWeight: FontWeight.w700,
          ),
        ),
      );

  Widget _corner(String text, Color color, {required bool left}) => Positioned(
        left: left ? -3 : null,
        right: left ? null : -3,
        top: -1,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: const Color.fromRGBO(0, 0, 0, 0.35)),
          ),
          child: Text(
            text,
            style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.w700),
          ),
        ),
      );

  Widget _dot(String text, Color color) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(8)),
        child: Text(text, style: const TextStyle(color: Colors.white, fontSize: 9)),
      );
}
