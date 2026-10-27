import 'dart:convert';
import 'dart:io';
import 'package:nutripulse/core/api.dart';
import 'package:nutripulse/core/data.dart';

void check(bool ok, String text) {
  if (!ok) throw StateError(text);
  stdout.writeln('PASS $text');
}

Future<void> main(List<String> args) async {
  if (args.length != 2) {
    throw ArgumentError(
      'Usage: dart run tool/verify_agents.dart QA_SERVER_URL TEST_JPEG',
    );
  }
  final api = ApiClient(baseUrl: args[0]);
  try {
    final scan = PendingWrite('/food-scans', {
      'image_base64': base64Encode(await File(args[1]).readAsBytes()),
      'mime_type': 'image/jpeg',
    });
    final result = await scan.send(api);
    check(
      result['status'] == 'REVIEW_REQUIRED' &&
          result.obj('result').rows('items').isNotEmpty,
      'vision response enters human review',
    );
    final item = result.obj('result').rows('items').first;
    final reviewed = {
      'local_date': today(),
      'meal_type': 'snack',
      'items': [
        {
          'display_name': item['name'],
          'amount': 120,
          'grams': 120,
          'unit': 'g',
          'kcal': 139.2,
          'carb_g': 31.1,
          'protein_g': 3.1,
          'fat_g': .4,
          'user_edited': true,
        },
      ],
    };
    final meal = await api.post(
      '/food-scans/${result['id']}/confirm',
      reviewed,
    );
    final again = await api.post(
      '/food-scans/${result['id']}/confirm',
      reviewed,
    );
    check(
      meal['id'] == again['id'] && meal['status'] == 'CONSUMED',
      'reviewed photo confirms exactly one consumed meal',
    );
    check(
      meal.rows('items').first.n('grams') == 120,
      'manual photo correction is preserved',
    );
    final chat = await api.post('/agent/chats');
    await api.post('/agent/chats/${chat['id']}/messages', {
      'content': '今天想吃清淡一点',
    });
    final reply = await api.post('/agent/chats/${chat['id']}/messages', {
      'content': '请给我一份晚餐方案',
    });
    check(
      reply.obj('proposal').rows('items').isNotEmpty,
      'multi-turn chat returns a server-validated proposal',
    );
    final history = await api.get('/agent/chats/${chat['id']}');
    check(
      history.rows('messages').length == 4 &&
          history
              .rows('messages')
              .every((m) => m.s('content_redacted').isNotEmpty),
      'conversation can reopen with full visible message history',
    );
    final accepted = await api.post('/agent/chats/${chat['id']}/accept');
    final acceptedAgain = await api.post('/agent/chats/${chat['id']}/accept');
    check(
      accepted['meal_id'] == acceptedAgain['meal_id'] &&
          accepted['status'] == 'PLANNED',
      'confirmed chat proposal creates one planned meal',
    );
  } finally {
    api.close();
  }
}
