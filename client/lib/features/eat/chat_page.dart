import 'package:flutter/material.dart';
import '../../core/app_scope.dart';
import '../../core/data.dart';
import '../../ui/design.dart';

Future<void> openChat(BuildContext context) async {
  final app = AppScope.of(context);
  final saved = await app.device.read('chat:${app.api.baseUrl}');
  String id;
  if (saved != null &&
      context.mounted &&
      await confirm(context, '继续上次饮食对话？', '可以接着描述口味、食材和用餐需求。', label: '继续对话')) {
    id = saved;
  } else {
    id = (await app.api.post('/agent/chats')).s('id');
    await app.device.write('chat:${app.api.baseUrl}', id);
  }
  if (context.mounted) {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => ChatPage(id: id)),
    );
  }
}

class ChatPage extends StatefulWidget {
  final String id;
  const ChatPage({super.key, required this.id});
  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final input = TextEditingController();
  List<Json> messages = [];
  Json? proposal;
  bool busy = false, started = false, ended = false;
  String? error;
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!started) {
      started = true;
      load();
    }
  }

  Future<void> load() async {
    final app = AppScope.of(context);
    await runTask(context, () async {
      final chat = await app.api.get('/agent/chats/${widget.id}');
      if (mounted) {
        setState(() {
          messages = chat
              .rows('messages')
              .map((m) => {...m, 'content': m['content_redacted']})
              .toList();
          ended = chat.obj('session')['status'] != 'ACTIVE';
          proposal = messages
              .where(
                (m) =>
                    m['role'] == 'assistant' && m['structured_payload'] != null,
              )
              .lastOrNull
              ?.obj('structured_payload');
        });
      }
    });
  }

  Future<void> send() async {
    final content = input.text.trim();
    if (content.isEmpty || content.length > 1000) {
      message(context, '请输入1–1000字的需求');
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final reply = await AppScope.of(
        context,
      ).api.post('/agent/chats/${widget.id}/messages', {'content': content});
      if (!mounted) return;
      setState(() {
        messages.add({'role': 'user', 'content': content});
        messages.add({'role': 'assistant', 'content': reply['reply']});
        proposal = reply['proposal'] == null ? null : reply.obj('proposal');
        input.clear();
      });
    } on Exception catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  void dispose() {
    input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('AI 饮食顾问')),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  Panel(
                    color: P.softGreen,
                    child: note('告诉我你想吃什么、有什么食材或准备在哪用餐。方案只会在你确认后预记入饮食页。'),
                  ),
                  for (final m in messages)
                    Align(
                      alignment: m['role'] == 'user'
                          ? Alignment.centerRight
                          : Alignment.centerLeft,
                      child: Container(
                        constraints: const BoxConstraints(maxWidth: 340),
                        margin: const EdgeInsets.only(bottom: 12),
                        child: Panel(
                          color: m['role'] == 'user'
                              ? P.softGreen
                              : Colors.white,
                          child: Text(m.s('content')),
                        ),
                      ),
                    ),
                  if (proposal != null)
                    Panel(
                      color: const Color(0xFFF0F8FD),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          section('待确认方案'),
                          if (proposal!['recipe_name'] != null)
                            Text(
                              proposal!.s('recipe_name'),
                              style: const TextStyle(
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          for (final item in proposal!.rows('items'))
                            ListTile(
                              contentPadding: EdgeInsets.zero,
                              title: Text(item.s('name')),
                              subtitle: Text(
                                '${display(item['grams'])}g · ${display(item['kcal'])} kcal',
                              ),
                              trailing: Text(
                                ((item['allergens'] as List?) ?? []).join('、'),
                              ),
                            ),
                          note(
                            '估算价格 ${proposal!['estimated_cost_cny'] == null ? '未知' : '¥${proposal!['estimated_cost_cny']}'}',
                          ),
                          note(
                            '碳水 ${display(knownTotal(proposal!.rows('items'), 'carb_g'), 1)}g · 蛋白 ${display(knownTotal(proposal!.rows('items'), 'protein_g'), 1)}g · 脂肪 ${display(knownTotal(proposal!.rows('items'), 'fat_g'), 1)}g',
                          ),
                          action(
                            '确认方案并加入饮食计划',
                            busy || ended
                                ? null
                                : () => runTask(context, () async {
                                    if (!await confirm(
                                      context,
                                      '确认预记入饮食页？',
                                      '加入计划后不计入实际摄入，吃过后再确认。',
                                    )) {
                                      return;
                                    }
                                    setState(() => busy = true);
                                    try {
                                      await app.api.post(
                                        '/agent/chats/${widget.id}/accept',
                                      );
                                      await app.device.write(
                                        'chat:${app.api.baseUrl}',
                                        null,
                                      );
                                      app.navigate(0);
                                      if (context.mounted) {
                                        Navigator.pop(context);
                                      }
                                    } finally {
                                      if (mounted) setState(() => busy = false);
                                    }
                                  }),
                          ),
                        ],
                      ),
                    ),
                  if (ended) note('此对话已结束，请返回创建新对话。'),
                  if (error != null)
                    Text(error!, style: const TextStyle(color: P.red)),
                ],
              ),
            ),
            if (busy) const LinearProgressIndicator(color: P.green),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: TextField(
                      controller: input,
                      enabled: !busy && !ended,
                      minLines: 1,
                      maxLines: 4,
                      maxLength: 1000,
                      decoration: const InputDecoration(
                        hintText: '例如：今晚想吃清淡一点，只有30分钟',
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: busy || ended ? null : send,
                    icon: const Icon(Icons.send_rounded),
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
