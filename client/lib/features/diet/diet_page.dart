import 'dart:convert';
import 'package:flutter/material.dart';
import '../../core/api.dart';
import '../../core/app_scope.dart';
import '../../core/data.dart';
import '../../ui/design.dart';
import '../../ui/forms.dart';
import 'meal_editor.dart';
import 'scan_page.dart';

class DietPage extends StatefulWidget {
  const DietPage({super.key});
  @override
  State<DietPage> createState() => _DietPageState();
}

class _DietPageState extends State<DietPage> {
  DateTime date = userToday();
  String lastToday = today();
  int dateRevision = 0;
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    if (dayString(date) == lastToday) date = userToday();
    lastToday = today();
    final day = dayString(date);
    return RemoteData<Json>(
      revision: app.revision + dateRevision,
      load: () => app.api.get('/nutrition/days/$day'),
      errorBuilder: (error) => PageBody(
        children: [
          title('饮食日记', subtitle: '$day · 电脑服务未连接'),
          Panel(
            child: Column(
              children: [
                Text(error.toString()),
                const SizedBox(height: 12),
                action('重新连接', app.refresh),
              ],
            ),
          ),
          const PendingBanner('meal'),
          const PendingBanner('water'),
          banner(
            '先记录一餐',
            '连接失败时保留原请求，可稍后重试',
            Icons.edit_outlined,
            () => mealSheet(context, day, 'lunch'),
          ),
          banner(
            '拍照识餐',
            '联网 Agent 需要电脑服务在线',
            Icons.camera_alt_outlined,
            () => chooseScan(context, day),
          ),
          const ArticleFeed(),
        ],
      ),
      builder: (data) {
        final summary = data.obj('summary'),
            energy = summary.obj('energy'),
            target = summary.obj('target');
        final hasTarget = summary['has_target'] == true;
        return PageBody(
          refresh: () async => app.refresh(),
          children: [
            title(
              '${userNow().hour < 11
                  ? '早安'
                  : userNow().hour < 18
                  ? '午安'
                  : '晚上好'}，朋友 👋',
              subtitle: 'DIET HUB · 控摄入，看结构',
              trailing: pill(
                '${date.month}月${date.day}日⌄',
                onTap: () async {
                  final selected = await showDatePicker(
                    context: context,
                    initialDate: date,
                    firstDate: DateTime(2020),
                    lastDate: userToday().add(const Duration(days: 90)),
                  );
                  if (selected != null && mounted) {
                    setState(() {
                      date = selected;
                      dateRevision++;
                    });
                  }
                },
              ),
            ),
            const PendingBanner('meal'),
            const PendingBanner('water'),
            Panel(
              child: Column(
                children: [
                  const Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      '今日能量预算',
                      style: TextStyle(
                        color: P.deepGreen,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: 174,
                    height: 174,
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        SizedBox.expand(
                          child: CircularProgressIndicator(
                            value: hasTarget && target.n('kcal') > 0
                                ? (energy.n('intake_kcal') / target.n('kcal'))
                                      .clamp(0, 1)
                                : 0,
                            strokeWidth: 12,
                            color: P.green,
                            backgroundColor: P.softGreen,
                            strokeCap: StrokeCap.round,
                          ),
                        ),
                        Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Text(
                              '还可摄入',
                              style: TextStyle(color: P.muted, fontSize: 12),
                            ),
                            Text(
                              hasTarget
                                  ? display(energy['remaining_kcal'])
                                  : '--',
                              style: const TextStyle(
                                fontSize: 36,
                                fontWeight: FontWeight.w800,
                                color: P.deepGreen,
                              ),
                            ),
                            const Text(
                              'kcal',
                              style: TextStyle(color: P.muted),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 17),
                  Text(
                    '目标 ${display(target['kcal'])} · 已摄入 ${display(energy['intake_kcal'])} · 运动 ${display(energy['activity_kcal'])}',
                    style: const TextStyle(fontSize: 12, color: P.muted),
                  ),
                  const SizedBox(height: 17),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF1F8FC),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      children: [
                        macro(
                          '碳水',
                          summary.obj('macros')['carb_g'],
                          target['carb_g'],
                          P.green,
                        ),
                        macro(
                          '蛋白质',
                          summary.obj('macros')['protein_g'],
                          target['protein_g'],
                          P.blue,
                        ),
                        macro(
                          '脂肪',
                          summary.obj('macros')['fat_g'],
                          target['fat_g'],
                          P.yellow,
                        ),
                      ],
                    ),
                  ),
                  if (summary.n('incomplete_macro_items') > 0)
                    note(
                      '${summary['incomplete_macro_items']} 项食物的宏量未完整填写，占比仅统计已知值',
                      color: P.red,
                    ),
                  if (!hasTarget) note('完善个人身体档案并选择阶段目标，生成每日预算。'),
                ],
              ),
            ),
            banner(
              '极速拍照打卡',
              'AI 识别食物，核对克数与热量后入账',
              Icons.camera_alt_outlined,
              () => chooseScan(context, day),
            ),
            FutureBuilder<Json?>(
              future: app.device.photoDraft(),
              builder: (context, state) => state.hasData
                  ? Panel(
                      color: P.softGreen,
                      child: Row(
                        children: [
                          const Expanded(child: Text('有一张加密保存在本机的识餐草稿')),
                          TextButton(
                            onPressed: () => runTask(context, () async {
                              final draft = state.data!;
                              await Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (_) => ScanPage(
                                    bytes: draft['bytes'],
                                    operation: draft.s('key'),
                                    date: day,
                                  ),
                                ),
                              );
                            }),
                            child: const Text('重试'),
                          ),
                          IconButton(
                            onPressed: () => runTask(context, () async {
                              if (await confirm(
                                context,
                                '删除本机照片草稿？',
                                '删除后无法恢复。',
                              )) {
                                await app.device.clearPhotoDraft();
                                app.refresh();
                              }
                            }),
                            icon: const Icon(Icons.delete_outline),
                          ),
                        ],
                      ),
                    )
                  : const SizedBox.shrink(),
            ),
            section(
              '今日饮食',
              trailing: Text(
                '${data.rows('meals').length} 条记录',
                style: const TextStyle(color: P.muted, fontSize: 12),
              ),
            ),
            for (final meal in mealNames.entries)
              mealCard(
                context,
                meal.key,
                meal.value,
                data
                    .rows('meals')
                    .where((m) => m['meal_type'] == meal.key)
                    .toList(),
                day,
              ),
            Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  section(
                    '饮水进度',
                    trailing: const Icon(
                      Icons.water_drop_outlined,
                      color: P.cyan,
                    ),
                  ),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      metric('今日饮水 ml', summary['water_ml'], color: P.cyan),
                      metric('目标 ml', target['water_ml']),
                    ],
                  ),
                  const SizedBox(height: 12),
                  LinearProgressIndicator(
                    value: target.n('water_ml') > 0
                        ? (summary.n('water_ml') / target.n('water_ml')).clamp(
                            0,
                            1,
                          )
                        : 0,
                    color: P.cyan,
                    backgroundColor: const Color(0xFFE6F9FA),
                    minHeight: 7,
                    borderRadius: BorderRadius.circular(5),
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 6,
                    children: [
                      for (final ml in [200, 300, 500])
                        pill(
                          '+$ml ml',
                          color: P.cyan,
                          onTap: () => runTask(context, () async {
                            await persistAndSend(
                              app,
                              'water',
                              PendingWrite('/water-logs', {
                                'local_date': day,
                                'amount_ml': ml,
                              }),
                            );
                          }),
                        ),
                      pill(
                        '修正总量',
                        onTap: () => editSheet(
                          context,
                          '修正 $day 饮水',
                          [
                            Field(
                              'total_ml',
                              '当日总量 ml',
                              value: summary['water_ml'],
                              numeric: true,
                              integer: true,
                              required: true,
                              min: 0,
                              max: 10000,
                            ),
                          ],
                          (body) async {
                            await app.api.put('/water-logs/days/$day', body);
                            app.refresh();
                          },
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            Panel(
              child: Row(
                children: [
                  const Icon(
                    Icons.directions_walk_rounded,
                    size: 31,
                    color: P.green,
                  ),
                  const SizedBox(width: 13),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${summary['steps_source'] == null ? '--' : display(summary['steps'])} 步',
                          style: const TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        note(
                          summary['steps_source'] == null
                              ? '连接运动设备后同步步数'
                              : '${summary['steps_source']} · 同步 ${summary['steps_synced_at']}',
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const ArticleFeed(),
          ],
        );
      },
    );
  }

  Widget macro(String label, dynamic value, dynamic target, Color color) =>
      Expanded(
        child: Column(
          children: [
            Text(
              label,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.w700,
                fontSize: 12,
              ),
            ),
            const SizedBox(height: 5),
            Text(
              '${display(value, 1)} / ${display(target)}g',
              style: const TextStyle(fontSize: 11),
            ),
          ],
        ),
      );
  Widget mealCard(
    BuildContext context,
    String key,
    String label,
    List<Json> meals,
    String day,
  ) {
    final app = AppScope.of(context);
    final eaten = meals
        .where((m) => m['status'] == 'CONSUMED')
        .expand((m) => m.rows('items'))
        .fold<double>(0, (sum, i) => sum + i.n('kcal'));
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(9),
                decoration: BoxDecoration(
                  color: P.softGreen,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  key == 'breakfast'
                      ? Icons.wb_sunny_outlined
                      : key == 'dinner'
                      ? Icons.nightlight_outlined
                      : Icons.rice_bowl_outlined,
                  color: P.deepGreen,
                  size: 21,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 16,
                  ),
                ),
              ),
              Text(
                '${display(eaten)} kcal',
                style: const TextStyle(fontSize: 12, color: P.muted),
              ),
              IconButton(
                tooltip: '添加$label',
                onPressed: () => mealSheet(context, day, key),
                icon: const Icon(Icons.add_circle_outline, color: P.green),
              ),
            ],
          ),
          if (meals.isEmpty) note('还没有记录，点击 + 添加'),
          for (final meal in meals)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Divider(color: P.line),
                  for (final item in meal.rows('items'))
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${item['display_name']} · ${display(item['amount'], 1)}${item['unit']}',
                            style: const TextStyle(fontSize: 13),
                          ),
                        ),
                        Text(
                          '${display(item['kcal'])} kcal',
                          style: const TextStyle(fontSize: 12, color: P.muted),
                        ),
                      ],
                    ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      pill(
                        meal['status'] == 'PLANNED' ? '计划 · 尚未计入摄入' : '已吃过',
                        color: meal['status'] == 'PLANNED'
                            ? P.blue
                            : P.deepGreen,
                      ),
                      if (meal['status'] == 'PLANNED')
                        pill(
                          '确认吃过',
                          onTap: () => runTask(context, () async {
                            await app.api.patch('/meals/${meal['id']}', {
                              'status': 'CONSUMED',
                            });
                            app.refresh();
                          }),
                        ),
                      pill(
                        '编辑',
                        onTap: () =>
                            mealSheet(context, day, key, original: meal),
                      ),
                      pill(
                        '删除',
                        color: P.red,
                        onTap: () => runTask(context, () async {
                          if (!await confirm(
                            context,
                            '删除餐食记录？',
                            '删除后可在 5 秒内撤销。',
                          )) {
                            return;
                          }
                          await app.api.delete('/meals/${meal['id']}');
                          app.refresh();
                          if (!context.mounted) return;
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              duration: const Duration(seconds: 4),
                              content: const Text('餐食已删除'),
                              action: SnackBarAction(
                                label: '撤销',
                                onPressed: () => runTask(context, () async {
                                  await app.api.post(
                                    '/meals/${meal['id']}/restore',
                                  );
                                  app.refresh();
                                }),
                              ),
                            ),
                          );
                        }),
                      ),
                    ],
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class ArticleFeed extends StatefulWidget {
  const ArticleFeed({super.key});
  @override
  State<ArticleFeed> createState() => _ArticleFeedState();
}

class _ArticleFeedState extends State<ArticleFeed> {
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    return RemoteData<Json>(
      revision: app.revision,
      load: () async {
        try {
          final result = await app.api.get('/articles');
          await app.device.write(
            'articles:${app.api.baseUrl}',
            jsonEncode({
              'items': result['items'],
              'saved_at': DateTime.now().toIso8601String(),
            }),
          );
          return result;
        } on ApiException {
          final cached = await app.device.read('articles:${app.api.baseUrl}');
          if (cached == null) rethrow;
          return object(jsonDecode(cached));
        }
      },
      builder: (data) {
        final items = data.rows('items');
        if (items.isEmpty) return const SizedBox.shrink();
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            section('每日健康资讯'),
            if (data['saved_at'] != null) note('离线缓存 · ${data['saved_at']}'),
            SizedBox(
              height: 226,
              child: PageView(
                children: items
                    .map(
                      (item) => Padding(
                        padding: const EdgeInsets.only(right: 4),
                        child: Panel(
                          padding: EdgeInsets.zero,
                          child: InkWell(
                            onTap: () => runTask(
                              context,
                              () => app.device.openUrl(item.s('source_url')),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                ClipRRect(
                                  borderRadius: const BorderRadius.vertical(
                                    top: Radius.circular(16),
                                  ),
                                  child: item.s('cover_url').isEmpty
                                      ? Container(
                                          height: 125,
                                          color: P.softGreen,
                                          alignment: Alignment.center,
                                          child: const Icon(
                                            Icons.eco,
                                            size: 45,
                                            color: P.green,
                                          ),
                                        )
                                      : Image.network(
                                          item.s('cover_url'),
                                          height: 125,
                                          width: double.infinity,
                                          fit: BoxFit.cover,
                                          errorBuilder: (_, error, stack) =>
                                              Container(
                                                height: 125,
                                                color: P.softGreen,
                                                child: const Center(
                                                  child: Icon(
                                                    Icons.eco,
                                                    color: P.green,
                                                  ),
                                                ),
                                              ),
                                        ),
                                ),
                                Padding(
                                  padding: const EdgeInsets.fromLTRB(
                                    14,
                                    10,
                                    14,
                                    0,
                                  ),
                                  child: Text(
                                    item.s('title'),
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                ),
                                Padding(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 14,
                                  ),
                                  child: note(item.s('source')),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
            note('左右滑动查看资讯，点击阅读原文'),
          ],
        );
      },
    );
  }
}
