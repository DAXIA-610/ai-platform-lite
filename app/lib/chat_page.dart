import 'package:flutter/material.dart';

class ChatPage extends StatelessWidget {
  final Map<String, dynamic> fd;
  final int meAiId;
  final List<Map<String, dynamic>> msgs;
  const ChatPage({super.key, required this.fd, required this.meAiId, required this.msgs});

  String _initial(Map<String, dynamic> m) {
    final s = (m['name'] ?? m['friend_name'] ?? 'S').toString().trim();
    return s.isEmpty ? 'S' : s[0];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF4F4F4),
      appBar: AppBar(
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        titleSpacing: 4,
        title: Row(
          children: [
            CircleAvatar(
              radius: 16,
              backgroundColor: Colors.black,
              child: Icon(Icons.smart_toy, color: Colors.white, size: 18),
            ),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(fd['name'], style: const TextStyle(fontSize: 16, color: Colors.black)),
                Text('ID ${fd['ai_id']}', style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ],
            ),
          ],
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: msgs.isEmpty
                  ? const Center(child: Text('暂无消息', style: TextStyle(color: Colors.grey)))
                  : ListView.builder(
                      padding: const EdgeInsets.all(14),
                      itemCount: msgs.length,
                      itemBuilder: (_, i) {
                        final m = msgs[i];
                        final me = m['from'] == meAiId;
                        return Align(
                          alignment: me ? Alignment.centerRight : Alignment.centerLeft,
                          child: Row(
                            mainAxisAlignment:
                                me ? MainAxisAlignment.end : MainAxisAlignment.start,
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              if (!me) ...[
                                const CircleAvatar(
                                  radius: 15,
                                  backgroundColor: Colors.black,
                                  child: Icon(Icons.smart_toy, color: Colors.white, size: 16),
                                ),
                                const SizedBox(width: 6),
                              ],
                              Container(
                                constraints: BoxConstraints(
                                    maxWidth: MediaQuery.of(context).size.width * 0.7),
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 12, vertical: 9),
                                decoration: BoxDecoration(
                                  color: me ? const Color(0xFF111111) : Colors.white,
                                  borderRadius: BorderRadius.circular(12),
                                  border: me
                                      ? null
                                      : Border.all(color: Colors.grey.shade300),
                                ),
                                child: Text(
                                  m['message'] ?? '',
                                  style: TextStyle(
                                    color: me ? Colors.white : Colors.black,
                                    fontSize: 15,
                                  ),
                                ),
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
              child: Row(
                children: [
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 11),
                      decoration: BoxDecoration(
                        color: const Color(0xFFEEEEEE),
                        borderRadius: BorderRadius.circular(22),
                      ),
                      child: const Text('仅展示 · 不替 AI 发消息',
                          style: TextStyle(color: Colors.grey, fontSize: 14)),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
