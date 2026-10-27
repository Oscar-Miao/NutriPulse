import 'dart:math';

typedef Json = Map<String, dynamic>;

Json object(dynamic value) =>
    value == null ? {} : Map<String, dynamic>.from(value as Map);
List<Json> records(dynamic value) =>
    value == null ? [] : (value as List).map(object).toList();

extension JsonValues on Json {
  Json obj(String key) => object(this[key]);
  List<Json> rows(String key) => records(this[key]);
  double n(String key) => (this[key] as num?)?.toDouble() ?? 0;
  String s(String key) => this[key]?.toString() ?? '';
}

String display(dynamic value, [int digits = 0]) =>
    value is num ? value.toStringAsFixed(digits) : '--';
double? knownTotal(List<Json> items, String key) =>
    items.every((item) => item[key] is num)
    ? items.fold<double>(0, (sum, item) => sum + (item[key] as num).toDouble())
    : null;
String dayString(DateTime value) =>
    '${value.year}-${value.month.toString().padLeft(2, '0')}-${value.day.toString().padLeft(2, '0')}';
DateTime userNow() => DateTime.now().toUtc().add(const Duration(hours: 8));
DateTime userToday() {
  final now = userNow();
  return DateTime(now.year, now.month, now.day);
}

String today() => dayString(userToday());
String operationKey() {
  final r = Random.secure();
  return List.generate(
    16,
    (_) => r.nextInt(256).toRadixString(16).padLeft(2, '0'),
  ).join();
}

const mealNames = {
  'breakfast': '早餐',
  'lunch': '午餐',
  'dinner': '晚餐',
  'snack': '加餐与饮品',
};
const goalNames = {
  'fat_loss': '减脂',
  'maintenance': '维持健康',
  'muscle_gain': '增肌',
  'recovery': '恢复期',
};
const scenarioNames = {
  'self_cook': '自己下厨',
  'takeout': '外卖',
  'dine_in': '堂食',
  'convenience': '便利店',
};
const workoutNames = {
  'walking': '步行',
  'running': '跑步',
  'cycling': '骑行',
  'swimming': '游泳',
  'strength': '力量训练',
  'yoga': '瑜伽',
  'custom': '自定义',
};
List<String> words(String value) => value
    .split(RegExp('[,，\n]'))
    .map((s) => s.trim())
    .where((s) => s.isNotEmpty)
    .toList();

({String start, String end}) periodRange(String period, DateTime end) {
  final start = switch (period) {
    'day' => end,
    'week' => end.subtract(const Duration(days: 6)),
    'month' => DateTime(end.year, end.month, 1),
    'year' => DateTime(end.year, 1, 1),
    _ => throw ArgumentError.value(period, 'period'),
  };
  return (start: dayString(start), end: dayString(end));
}

bool safeServerUrl(String value) {
  final uri = Uri.tryParse(value);
  if (uri == null ||
      !uri.hasAuthority ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      (uri.path.isNotEmpty && uri.path != '/')) {
    return false;
  }
  if (uri.scheme == 'https') return true;
  if (uri.scheme != 'http') return false;
  if (['localhost', '127.0.0.1', '::1'].contains(uri.host)) return true;
  final parts = uri.host.split('.').map(int.tryParse).toList();
  if (parts.length != 4 || parts.any((n) => n == null || n < 0 || n > 255)) {
    return false;
  }
  return parts[0] == 10 ||
      (parts[0] == 192 && parts[1] == 168) ||
      (parts[0] == 172 && parts[1]! >= 16 && parts[1]! <= 31);
}
