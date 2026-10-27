import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nutripulse/core/api.dart';
import 'package:nutripulse/core/app_scope.dart';
import 'package:nutripulse/core/data.dart';
import 'package:nutripulse/core/native_device.dart';
import 'package:nutripulse/main.dart';

class MemoryDevice extends NativeDevice {
  final values = <String, String>{};
  final cleared = <String>[];
  bool revoked = false;
  @override
  Future<void> clearLocal(String category) async {
    cleared.add(category);
  }

  @override
  Future<void> revokeHealth() async {
    revoked = true;
  }

  @override
  Future<String?> read(String key) async => values[key];
  @override
  Future<void> write(String key, String? value) async {
    if (value == null) {
      values.remove(key);
    } else {
      values[key] = value;
    }
  }

  @override
  Future<Json?> photoDraft() async => null;
}

class HealthFixture extends MemoryDevice {
  @override
  Future<Json> healthSamples({bool requestPermission = true}) async => {
    'samples': List.generate(
      501,
      (i) => {
        'external_id': 'qa-$i',
        'sample_type': 'active_energy',
        'value': 1,
      },
    ),
    'energy_allowed': true,
    'scopes': ['android.permission.health.READ_ACTIVE_CALORIES_BURNED'],
  };
}

class HealthApi extends FixtureApi {
  @override
  Future<Json> request(
    String method,
    String path, {
    Json? data,
    String? key,
  }) async {
    calls.add({'method': method, 'path': path, 'data': data});
    return path == '/devices'
        ? {'id': 'connection'}
        : {'imported': (data!['samples'] as List).length};
  }
}

class FixtureApi extends ApiClient {
  final calls = <Json>[];
  bool offline = false;
  final meal = <String, dynamic>{
    'id': 'meal1',
    'meal_type': 'breakfast',
    'status': 'PLANNED',
    'items': [
      {'display_name': '测试早餐', 'amount': 100, 'unit': 'g', 'kcal': 116},
    ],
  };
  Json get target => {
    'kcal': 2000,
    'bmr_kcal': 1500,
    'tdee_kcal': 2200,
    'carb_g': 240,
    'protein_g': 120,
    'fat_g': 60,
    'water_ml': 2400,
  };
  @override
  Future<Json> request(
    String method,
    String path, {
    Json? data,
    String? key,
  }) async {
    calls.add({'method': method, 'path': path, 'data': data});
    if (offline) throw ApiException('测试：电脑服务未连接');
    if (path == '/profile') {
      return {
        'profile': {'display_name': '朋友', 'activity_level': 'moderate'},
        'target': target,
        'measurement': {},
        'training': {},
        'goal': {},
        'allergies': [],
        'restrictions': [],
        'preferences': [],
        'dining': {'flavors': [], 'preferred_scenario': 'self_cook'},
      };
    }
    if (method == 'PATCH' && path == '/meals/meal1') {
      meal['status'] = data!['status'];
      return meal;
    }
    final summary = {
      'has_target': true,
      'target': target,
      'energy': {
        'remaining_kcal': 2000,
        'intake_kcal': meal['status'] == 'CONSUMED' ? 116 : 0,
        'activity_kcal': 0,
      },
      'macros': {},
      'water_ml': 0,
      'activity_goal_kcal': 300,
      'steps_source': null,
      'incomplete_macro_items': 0,
    };
    if (path.startsWith('/nutrition/days')) {
      return {
        'summary': summary,
        'meals': [meal],
      };
    }
    if (path.startsWith('/fitness/days')) {
      return {'summary': summary, 'active_plan': {}, 'workouts': []};
    }
    if (path.startsWith('/analytics/days')) return summary;
    if (path.startsWith('/analytics/energy')) return {'series': []};
    if (path.startsWith('/analytics/macros')) {
      return {'actual': {}, 'target': {}};
    }
    if (path.startsWith('/analytics/body-composition')) return {'series': []};
    if (path.startsWith('/analytics/habits')) {
      return {'water': {}, 'fiber': {}, 'meals': {}, 'training': {}};
    }
    return {'items': []};
  }
}

void main() {
  test(
    'profile erasure cannot race health synchronization and stops future imports',
    () async {
      final api = FixtureApi(), device = MemoryDevice();
      final app = AppController(api, device)..syncing = true;
      await expectLater(
        app.deletePersonal('profile', 'DELETE_PROFILE'),
        throwsA(isA<ApiException>()),
      );
      expect(api.calls, isEmpty);
      app.syncing = false;
      await device.write('health_auto_sync', 'true');
      await app.deletePersonal('profile', 'DELETE_PROFILE');
      expect(await device.read('health_auto_sync'), isNull);
      expect(device.revoked, isTrue);
      expect(device.cleared, ['profile']);
      expect(app.deleting, isFalse);
      api.close();
    },
  );
  test(
    'Health Connect chunks activate one complete batch after the final upload',
    () async {
      final api = HealthApi(), device = HealthFixture();
      final app = AppController(api, device);
      await app.syncHealth();
      final batches = api.calls
          .where((c) => c['path'] == '/devices/connection/samples')
          .map((c) => object(c['data']))
          .toList();
      expect(batches.length, 2);
      expect((batches.first['samples'] as List).length, 500);
      expect((batches.last['samples'] as List).length, 1);
      expect(batches.first['sync_batch_id'], batches.last['sync_batch_id']);
      expect(batches.first.containsKey('activate_active_dates'), isFalse);
      expect((batches.last['activate_active_dates'] as List).length, 7);
      expect(await device.read('health_auto_sync'), 'true');
      expect(app.syncing, isFalse);
      api.close();
    },
  );
  for (final width in [320.0, 390.0, 480.0]) {
    testWidgets('five tabs fit width $width and remain aligned', (
      tester,
    ) async {
      tester.view.physicalSize = Size(width, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final api = FixtureApi(),
          app = AppController(FixtureApi(), MemoryDevice());
      await tester.pumpWidget(NutriPulse(controller: app));
      await tester.pumpAndSettle();
      for (var i = 0; i < 5; i++) {
        await tester.tap(find.byKey(ValueKey('nav-$i')));
        await tester.pumpAndSettle();
        final exception = tester.takeException();
        if (exception is FlutterError) {
          for (final node in exception.diagnostics) {
            debugPrint(node.toStringDeep());
          }
        }
        expect(exception, isNull, reason: 'navigation tab $i at width $width');
      }
      final centers = List.generate(
        5,
        (i) => tester.getCenter(find.byKey(ValueKey('nav-$i'))),
      );
      expect(centers.every((p) => p.dy == centers.first.dy), isTrue);
      expect(centers[2].dx, closeTo(width / 2, 1));
      await tester.pumpWidget(const SizedBox());
      app.api.close();
      api.close();
    });
  }
  testWidgets(
    'planned meal is explicitly confirmed with PATCH then refreshes',
    (tester) async {
      tester.view.physicalSize = const Size(390, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final api = FixtureApi(),
          app = AppController(FixtureApi(), MemoryDevice());
      await tester.pumpWidget(NutriPulse(controller: app));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('确认吃过'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('确认吃过'));
      await tester.pumpAndSettle();
      expect((app.api as FixtureApi).meal['status'], 'CONSUMED');
      expect(
        (app.api as FixtureApi).calls.any(
          (c) => c['method'] == 'PATCH' && c['path'] == '/meals/meal1',
        ),
        isTrue,
      );
      await tester.pumpWidget(const SizedBox());
      app.api.close();
      api.close();
    },
  );
  testWidgets('connection editor remains reachable while server is offline', (
    tester,
  ) async {
    final api = FixtureApi()..offline = true,
        app = AppController(FixtureApi()..offline = true, MemoryDevice());
    await tester.pumpWidget(NutriPulse(controller: app));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('电脑连接设置'));
    await tester.pumpAndSettle();
    expect(find.text('连接本地电脑'), findsOneWidget);
    expect(find.text('服务地址'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    app.api.close();
    api.close();
  });
}
