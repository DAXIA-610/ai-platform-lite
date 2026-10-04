import 'package:flutter/material.dart';

/// 真心话大冒险房间的配色。宴会厅那一套——暗背景 + 羊皮纸 + 金边。
///
/// 全项目只有这一处写死颜色，组件里不要再散着写色值。
/// 注意：一律不用 `Color.withOpacity()`（新版 Flutter 里它已经被换掉了），
/// 半透明直接用 `Color.fromRGBO` 或带 alpha 的 `0xAARRGGBB` 常量。
class RoomTheme {
  RoomTheme._();

  // ---- 背景：暗色宴会厅 ----
  static const Color bgTop = Color(0xFF3A2A1B);
  static const Color bgMid = Color(0xFF241A10);
  static const Color bgBottom = Color(0xFF120C07);
  static const Color vignette = Color.fromRGBO(0, 0, 0, 0.55);

  // ---- 羊皮纸 ----
  static const Color paper = Color(0xFFF4E6C9);
  static const Color paperDark = Color(0xFFE2CDA4);
  static const Color paperEdge = Color(0xFFCBB183);
  static const Color ink = Color(0xFF3B2A18);
  static const Color inkSoft = Color(0xFF7C6748);

  // ---- 金 ----
  static const Color gold = Color(0xFFC9A227);
  static const Color goldSoft = Color(0xFFE2C97E);
  static const Color goldDeep = Color(0xFF8C6F14);

  // ---- 身份色：真人金边 / AI 蓝边 ----
  static const Color humanEdge = Color(0xFFC9A227);
  static const Color aiEdge = Color(0xFF4A7BA7);

  // ---- 两个选择 ----
  static const Color truthRed = Color(0xFFB4453C);   // 真心话
  static const Color dareBlue = Color(0xFF3E6B8C);   // 大冒险

  // ---- 状态 ----
  static const Color win = Color(0xFF2F7D6B);
  static const Color lose = Color(0xFFB4453C);
  static const Color thinking = Color(0xFF4A7BA7);

  /// 羊皮纸卡片的外观（书卷 / 面板共用）
  static BoxDecoration paperBox({
    double radius = 16,
    bool glowing = false,
  }) =>
      BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [paper, paperDark],
        ),
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(
          color: glowing ? gold : const Color.fromRGBO(201, 162, 39, 0.55),
          width: glowing ? 1.8 : 1.2,
        ),
        boxShadow: const [
          BoxShadow(color: Color.fromRGBO(0, 0, 0, 0.45), blurRadius: 18, offset: Offset(0, 8)),
        ],
      );

  /// 暗底上的玻璃感面板（顶部栏 / 底部栏用）
  static BoxDecoration barBox({double radius = 14}) => BoxDecoration(
        color: const Color.fromRGBO(30, 21, 13, 0.82),
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: const Color.fromRGBO(201, 162, 39, 0.28)),
      );

  /// 标题字
  static const TextStyle title = TextStyle(
    color: ink,
    fontSize: 16,
    fontWeight: FontWeight.w700,
    letterSpacing: 0.6,
  );

  static const TextStyle body = TextStyle(color: ink, fontSize: 14, height: 1.5);

  static const TextStyle hint = TextStyle(color: inkSoft, fontSize: 12.5, height: 1.4);

  static const TextStyle onDark = TextStyle(color: goldSoft, fontSize: 13, letterSpacing: 0.5);
}
