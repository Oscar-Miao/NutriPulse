import 'package:flutter_test/flutter_test.dart';
import 'package:nutripulse/core/api.dart';
import 'package:nutripulse/core/data.dart';
import 'package:nutripulse/features/diet/meal_editor.dart';
import 'package:nutripulse/features/fitness/prescription.dart';

class RecordingApi extends ApiClient {
  final List<Json> calls = [];
  @override
  Future<Json> post(String path, [Json? data, String? key]) async {
    calls.add({'path': path, 'data': data, 'key': key});
    return {'id': 'saved'};
  }
}

void main() {
  test('proposal totals never turn missing macros into known zero', () {
    expect(
      knownTotal([
        {'protein_g': 10},
        {'kcal': 20},
      ], 'protein_g'),
      isNull,
    );
    expect(
      knownTotal([
        {'protein_g': 0},
        {'protein_g': 10},
      ], 'protein_g'),
      10,
    );
  });
  test(
    'connection boundary permits private HTTP and rejects paths and credential URLs',
    () {
      for (final url in [
        'http://10.0.2.2:8787',
        'http://127.0.0.1:8787',
        'http://192.168.1.4:8787',
        'http://172.16.0.2:8787',
        'https://example.com',
      ]) {
        expect(safeServerUrl(url), isTrue, reason: url);
      }
      for (final url in [
        'http://example.com',
        'http://172.32.0.1',
        'http://192.168.1.4/api',
        'https://user:pass@example.com',
        'https://example.com?token=x',
        'https://example.com#x',
        'http://999.1.2.3',
        'file:///tmp/test',
      ]) {
        expect(safeServerUrl(url), isFalse, reason: url);
      }
    },
  );
  test('retry freezes the request body and key across serialization', () async {
    final payload = <String, dynamic>{
      'local_date': '2026-10-27',
      'items': [
        {'kcal': 100},
      ],
    };
    final write = PendingWrite(
      '/meals',
      payload,
      serverUrl: 'http://10.0.2.2:8787',
    );
    (payload['items'] as List).first['kcal'] = 999;
    final restored = PendingWrite.fromJson(write.toJson()),
        api = RecordingApi();
    await write.send(api);
    await restored.send(api);
    expect(api.calls[0]['data'], api.calls[1]['data']);
    expect(api.calls[0]['key'], api.calls[1]['key']);
    expect((api.calls[0]['data']['items'] as List).first['kcal'], 100);
    api.baseUrl = 'http://192.168.0.8:8787';
    expect(() => restored.send(api), throwsA(isA<ApiException>()));
    api.close();
  });
  test('calendar periods preserve leap days and cross-year weeks', () {
    expect(periodRange('week', DateTime(2026, 1, 2)).start, '2025-12-27');
    expect(periodRange('month', DateTime(2024, 2, 29)).start, '2024-02-01');
    expect(periodRange('year', DateTime(2024, 12, 31)).start, '2024-01-01');
  });
  test('plan prescriptions preserve seconds and bodyweight intent', () {
    final seconds = Prescription.parse('平板支撑 3×20秒');
    expect(
      (seconds.name, seconds.sets, seconds.amount, seconds.timed),
      ('平板支撑', 3, 20, true),
    );
    final reps = Prescription.parse('卧推 4×8-12');
    expect(
      (reps.name, reps.sets, reps.amount, reps.timed),
      ('卧推', 4, 8, false),
    );
  });
  test('meal editing retains unknown macros and explicit known zero', () {
    final fields = FoodFields({
      'display_name': '食物',
      'amount': 1,
      'unit': '份',
      'kcal': 100,
      'carb_g': 0,
      'protein_g': 8,
      'fat_g': 0,
      'fiber_g': 0,
      'nutrient_known_mask': 3,
    });
    final body = fields.payload();
    expect(body['carb_g'], 0);
    expect(body['protein_g'], 8);
    expect(body.containsKey('fat_g'), isFalse);
    expect(body.containsKey('fiber_g'), isFalse);
    fields.dispose();
  });
  test(
    'weighed food quantity scales nutrition and clears renamed food references',
    () {
      final fields = FoodFields({
        'food_id': 'rice',
        'display_name': '米饭',
        'amount': 100,
        'grams': 100,
        'unit': 'g',
        'kcal': 116,
        'carb_g': 25.9,
      });
      fields.controls['amount']!.text = '200';
      fields.changed('amount', '200');
      expect(fields.payload()['kcal'], 232);
      expect(fields.payload()['grams'], 200);
      expect(fields.payload()['carb_g'], 51.8);
      fields.controls['display_name']!.text = '其他食物';
      expect(fields.payload().containsKey('food_id'), isFalse);
      fields.dispose();
    },
  );
}
