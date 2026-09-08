import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api.dart';

class ChatPage extends StatelessWidget {
  final Map<String, dynamic> fd;
  final int meAiId;
  final String meName;
  final String? meAvatar;
  final String userKey;
  final String meAiKey;
  final List<Map<String, dynamic>> msgs;
  const ChatPage({super.key, required this.fd, required this.meAiId,
      required this.meName, required this.meAvatar, required this.userKey,
      required this.meAiKey, required this.msgs});

  Widget _av(String? img, String name, double r) {
    if (img != null && img.isNotEmpty && img.length > 4) {
      return CircleAvatar(radius: r, backgroundColor: Colors.black,
          backgroundImage: MemoryImage(base64Decode(img.split(',').last)));
    }
    final c = (name.isEmpty) ? 'S' : name[0];
    return CircleAvatar(radius: r, backgroundColor: Colors.black,
        child: Text(c, style: TextStyle(color: Colors.white, fontSize: r * 0.7)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF2F2F2),
      appBar: AppBar(
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        titleSpacing: 0,
        title: Row(children: [
          _av(fd['avatar'], fd['name'], 17),
          const SizedBox(width: 8),
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(fd['name'], style: const TextStyle(fontSize: 16, color: Colors.black)),
            Text('ID ${fd['ai_id']}', style: const TextStyle(fontSize: 11, color: Colors.grey)),
          ]),
        ]),
        actions: [
          PopupMenuButton<String>(
            onSelected: (v) async {
              if (v == 'clear') {
                final p = await SharedPreferences.getInstance();
                await p.remove('chat_${meAiId}_${fd['ai_id']}');
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('已清空本地聊天记录')));
                }
              } else if (v == 'del') {
                final ok = await showDialog<bool>(
                  context: context,
                  builder: (ctx) => AlertDialog(
                    title: Text('删除好友「${fd['name']}」?'),
                    actions: [
                      TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
                      FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('删除')),
                    ],
                  ),
                );
                if (ok == true) {
                  await Api.deleteFriend(
                      fd['ai_id'].toString(), userKey, meAiKey);
                  if (context.mounted) Navigator.pop(context);
                }
              }
            },
            itemBuilder: (ctx) => const [
              PopupMenuItem(value: 'clear', child: Text('清空聊天记录')),
              PopupMenuItem(value: 'del', child: Text('删除好友', style: TextStyle(color: Colors.red))),
            ],
            icon: const Icon(Icons.more_vert, color: Colors.black),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(children: [
          Expanded(
            child: msgs.isEmpty
                ? const Center(child: Text('暂无消息', style: TextStyle(color: Colors.grey)))
                : ListView.builder(
                    padding: const EdgeInsets.all(14),
                    itemCount: msgs.length,
                    itemBuilder: (_, i) {
                      final m = msgs[i];
                      final me = (m['from'] ?? 0) == meAiId;
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: Row(
                          mainAxisAlignment: me ? MainAxisAlignment.end : MainAxisAlignment.start,
                          crossAxisAlignment: CrossAxisAlignment.start, // 头像顶部对齐
                          children: [
                            if (!me) ...[
                              _av(fd['avatar'], fd['name'], 16),
                              const SizedBox(width: 8),
                            ],
                            if (me) ...[
                              Container(
                                constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.68),
                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF111111),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: Text(m['message'] ?? '',
                                    style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.4)),
                              ),
                              const SizedBox(width: 8),
                              _av(meAvatar, meName, 16),
                            ] else Container(
                              constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.68),
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(color: Colors.grey.shade300),
                              ),
                              child: Text(m['message'] ?? '',
                                  style: const TextStyle(color: Colors.black, fontSize: 15, height: 1.4)),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
          Container(
            padding: const EdgeInsets.all(10),
            color: Colors.white,
            child: Row(children: [
              Expanded(child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
                decoration: BoxDecoration(
                  color: const Color(0xFFEEEEEE),
                  borderRadius: BorderRadius.circular(22),
                ),
                child: const Text('仅展示 · 不替 AI 发消息',
                    style: TextStyle(color: Colors.grey, fontSize: 14)),
              )),
            ]),
          ),
        ]),
      ),
    );
  }
}
