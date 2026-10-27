import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'api.dart';
import 'data.dart';
import 'native_device.dart';

class AppController extends ChangeNotifier {
  final ApiClient api;
  final NativeDevice device;
  int tab = 0;
  int revision = 0;
  bool syncing = false;
  bool deleting = false;
  AppController(this.api, this.device);
  void refresh() {
    revision++;
    notifyListeners();
  }

  void navigate(int value) {
    tab = value;
    revision++;
    notifyListeners();
  }

  Future<void> syncHealth({bool requestPermission = true}) async {
    if (deleting) throw ApiException('正在清空个人数据，请完成后再同步设备');
    if (syncing) return;
    syncing = true;
    try {
      final health = await device.healthSamples(
        requestPermission: requestPermission,
      );
      final samples = health.rows('samples');
      final energyAllowed = health['energy_allowed'] == true;
      final connection = await api.post('/devices', {
        'provider': 'health_connect',
        'scopes': health['scopes'],
      });
      // Server accepts at most 500 samples per call. Each sample keeps its stable external ID.
      final batch = operationKey(), anchor = userToday();
      final batches = ((samples.length + 499) ~/ 500).clamp(1, 100000);
      for (var index = 0; index < batches; index++) {
        await api.post('/devices/${connection['id']}/samples', {
          'samples': samples.sublist(
            index * 500,
            ((index + 1) * 500).clamp(0, samples.length),
          ),
          if (energyAllowed) ...{
            'sync_batch_id': batch,
            'stage_active_energy': true,
            if (index == batches - 1)
              'activate_active_dates': List.generate(
                7,
                (i) => dayString(anchor.subtract(Duration(days: 6 - i))),
              ),
          },
        });
      }
      await device.write('health_auto_sync', 'true');
      refresh();
    } finally {
      syncing = false;
    }
  }

  Future<void> deletePersonal(String category, String phrase) async {
    if (deleting ||
        (syncing && ['fitness', 'profile', 'all'].contains(category))) {
      throw ApiException('设备正在同步或数据清空中，请完成后再操作');
    }
    deleting = true;
    try {
      await api.post('/privacy/delete', {
        'category': category,
        'confirmation_phrase': phrase,
      });
      try {
        if (['fitness', 'profile', 'all'].contains(category)) {
          await device.write('health_auto_sync', null);
        }
        await device.clearLocal(category);
        if (category == 'all') {
          api.token = '';
          api.baseUrl = 'http://10.0.2.2:8787';
        }
        if (['fitness', 'profile', 'all'].contains(category)) {
          await device.revokeHealth();
        }
      } on PlatformException catch (e) {
        throw ApiException('服务器数据已清空，本机草稿或健康权限清理失败，请在系统中核对授权', cause: e);
      } finally {
        refresh();
      }
    } finally {
      deleting = false;
    }
  }
}

class AppScope extends InheritedNotifier<AppController> {
  const AppScope({
    super.key,
    required AppController controller,
    required super.child,
  }) : super(notifier: controller);
  static AppController of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<AppScope>()!.notifier!;
}
