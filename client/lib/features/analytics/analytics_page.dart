import 'package:flutter/material.dart';
import '../../core/app_scope.dart';
import '../../core/data.dart';
import '../../ui/design.dart';
import 'charts.dart';

class AnalyticsPage extends StatefulWidget {
  const AnalyticsPage({super.key});
  @override
  State<AnalyticsPage> createState() => _AnalyticsPageState();
}

class _AnalyticsPageState extends State<AnalyticsPage> {
  String period = 'week';
  DateTime end = userToday();
  int selection = 0;
  Json? diagnosis;
  bool diagnosing = false;
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context), range = periodRange(period, end);
    final query = 'start=${range.start}&end=${range.end}';
    return RemoteData<List<Json>>(
      revision: app.revision + selection,
      load: () => Future.wait([
        app.api.get(
          '/analytics/energy?$query&granularity=${period == 'year' ? 'month' : 'day'}',
        ),
        app.api.get('/analytics/macros?$query'),
        app.api.get('/analytics/body-composition?$query'),
        app.api.get('/analytics/habits?$query'),
        app.api.get('/analytics/diagnostics?$query'),
      ]),
      builder: (data) {
        final series = data[0].rows('series'),
            macro = data[1],
            habits = data[3];
        double sum(String key) => series.fold(0, (a, s) => a + s.n(key));
        final targetDays = sum('target_days'), days = sum('days');
        final latest = diagnosis ?? data[4].rows('items').firstOrNull;
        final actual = macro.obj('actual'),
            grams = [
              actual.n('carb_g'),
              actual.n('protein_g'),
              actual.n('fat_g'),
            ];
        final macroEnergy = grams[0] * 4 + grams[1] * 4 + grams[2] * 9;
        return PageBody(
          refresh: () async => app.refresh(),
          children: [
            title('数据洞察', subtitle: 'ANALYTICS HUB · 看见每一天的改变'),
            SizedBox(
              width: double.infinity,
              child: SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'day', label: Text('日')),
                  ButtonSegment(value: 'week', label: Text('周')),
                  ButtonSegment(value: 'month', label: Text('月')),
                  ButtonSegment(value: 'year', label: Text('年')),
                ],
                selected: {period},
                showSelectedIcon: false,
                onSelectionChanged: (v) => setState(() {
                  period = v.first;
                  selection++;
                  diagnosis = null;
                }),
              ),
            ),
            const SizedBox(height: 12),
            Center(
              child: pill(
                '${range.start} — ${range.end} ⌄',
                onTap: () async {
                  final date = await showDatePicker(
                    context: context,
                    initialDate: end,
                    firstDate: DateTime(2020),
                    lastDate: userToday(),
                  );
                  if (date != null && mounted) {
                    setState(() {
                      end = date;
                      selection++;
                      diagnosis = null;
                    });
                  }
                },
              ),
            ),
            const SizedBox(height: 18),
            Row(
              children: [
                Expanded(
                  child: Panel(
                    padding: const EdgeInsets.symmetric(
                      vertical: 16,
                      horizontal: 4,
                    ),
                    child: metric(
                      '总摄入 kcal',
                      sum('intake_kcal'),
                      color: P.deepGreen,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Panel(
                    padding: const EdgeInsets.symmetric(
                      vertical: 16,
                      horizontal: 4,
                    ),
                    child: metric(
                      '净差 kcal',
                      targetDays > 0 ? sum('net_kcal') : null,
                      color: sum('net_kcal') > 0 ? P.red : P.blue,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Panel(
                    padding: const EdgeInsets.symmetric(
                      vertical: 16,
                      horizontal: 4,
                    ),
                    child: metric(
                      '容量 kg',
                      sum('training_volume'),
                      color: P.red,
                    ),
                  ),
                ),
              ],
            ),
            Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  section('能量平衡'),
                  note('摄入 ↑  ·  消耗 ↓  ·  净差为摄入减总消耗'),
                  SizedBox(
                    height: 220,
                    child: CustomPaint(
                      painter: EnergyPainter(series),
                      child: const SizedBox.expand(),
                    ),
                  ),
                  Wrap(
                    spacing: 10,
                    children: [
                      legend('摄入', P.green),
                      legend('总消耗', P.red),
                      legend('BMR', P.blue),
                      legend('净差', P.yellow),
                    ],
                  ),
                  note('BMR 为基础代谢参考线；总消耗使用服务端 TDEE 与活动去重结果。'),
                  if (targetDays < days)
                    note(
                      '仅 $targetDays / $days 天有营养目标；缺少目标的日期不计算消耗与净差。',
                      color: P.red,
                    ),
                  TextButton(
                    onPressed: () => detailSheet(context, series),
                    child: const Text('查看各期明细'),
                  ),
                ],
              ),
            ),
            Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  section('宏量营养供能结构'),
                  if (macroEnergy > 0)
                    ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: Row(
                        children: [
                          for (var i = 0; i < 3; i++)
                            if (grams[i] > 0)
                              Expanded(
                                flex: (grams[i] * (i == 2 ? 9 : 4) * 100)
                                    .round()
                                    .clamp(1, 100000000),
                                child: Container(
                                  height: 13,
                                  color: [P.green, P.blue, P.yellow][i],
                                ),
                              ),
                        ],
                      ),
                    ),
                  const SizedBox(height: 15),
                  Row(
                    children: [
                      for (var i = 0; i < 3; i++)
                        Expanded(
                          child: Column(
                            children: [
                              metric(
                                ['碳水 g', '蛋白质 g', '脂肪 g'][i],
                                grams[i],
                                color: [P.green, P.blue, P.yellow][i],
                                digits: 1,
                              ),
                              note(
                                macroEnergy == 0
                                    ? '--'
                                    : '${display(grams[i] * (i == 2 ? 9 : 4) * 100 / macroEnergy)}%',
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                  if (macro.n('incomplete_items') > 0)
                    note(
                      '${macro['incomplete_items']} 项食物的宏量不完整，结构仅反映已知值。',
                      color: P.red,
                    ),
                ],
              ),
            ),
            Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  section('体脂与周训练容量'),
                  SizedBox(
                    height: 190,
                    child: CustomPaint(
                      painter: TrendPainter(data[2].rows('series'), const [
                        TrendLine('body_fat_pct', '体脂 %', P.blue),
                        TrendLine(
                          'training_volume_kg',
                          '容量 kg',
                          P.red,
                          right: true,
                        ),
                      ]),
                      child: const SizedBox.expand(),
                    ),
                  ),
                  Wrap(
                    spacing: 12,
                    children: [
                      legend('左轴 体脂 %', P.blue),
                      legend('右轴 容量 kg', P.red),
                    ],
                  ),
                  note('缺失测量保留断点，不把无测量当作 0。'),
                  section('体重趋势'),
                  SizedBox(
                    height: 155,
                    child: CustomPaint(
                      painter: TrendPainter(data[2].rows('series'), const [
                        TrendLine('weight_kg', '体重 kg', P.green),
                      ]),
                      child: const SizedBox.expand(),
                    ),
                  ),
                ],
              ),
            ),
            Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  section(
                    'AI 营养诊断',
                    trailing: const Icon(Icons.auto_awesome, color: P.green),
                  ),
                  if (latest == null) note('结合所选周期的真实账本生成观察与建议。'),
                  if (latest != null) ...[
                    note(
                      '版本 ${latest['version'] ?? '--'} · 来源 ${latest['source']} · ${latest['created_at'] ?? ''}',
                    ),
                    for (final o in (latest['observations'] as List?) ?? [])
                      Text('• $o'),
                    const SizedBox(height: 10),
                    for (final a in (latest['advice'] as List?) ?? [])
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Text(a.toString()),
                      ),
                  ],
                  action(
                    diagnosing ? '正在分析…' : '生成本期诊断',
                    diagnosing
                        ? null
                        : () async {
                            setState(() => diagnosing = true);
                            await runTask(context, () async {
                              final value = await app.api.post(
                                '/analytics/diagnostics',
                                {'start': range.start, 'end': range.end},
                              );
                              if (mounted) setState(() => diagnosis = value);
                            });
                            if (mounted) setState(() => diagnosing = false);
                          },
                  ),
                  if (data[4].rows('items').isNotEmpty)
                    TextButton(
                      onPressed: () => showDialog(
                        context: context,
                        builder: (c) => SimpleDialog(
                          title: const Text('历史诊断版本'),
                          children: data[4]
                              .rows('items')
                              .map(
                                (item) => SimpleDialogOption(
                                  onPressed: () {
                                    setState(() => diagnosis = item);
                                    Navigator.pop(c);
                                  },
                                  child: Text(
                                    'v${item['version']} · ${item['source']}\n${item['created_at']}',
                                  ),
                                ),
                              )
                              .toList(),
                        ),
                      ),
                      child: const Text('查看历史版本'),
                    ),
                ],
              ),
            ),
            Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  section('习惯与恢复'),
                  note(
                    '饮水记录 ${habits.obj('water')['recorded_days']} 天 · 合计 ${display(habits.obj('water')['recorded_ml'])} ml\n饮水达标 ${habits.obj('water')['met_goal_days']} / ${habits.obj('water')['evaluated_goal_days']} 个可评估日',
                  ),
                  note(
                    '已知膳食纤维 ${display(habits.obj('fiber')['known_g'], 1)}g · 未知 ${habits.obj('fiber')['unknown_items']} 项',
                  ),
                  note(
                    '三餐记账覆盖 ${display(habits.obj('meals')['three_meal_logging_pct'], 1)}%\n计划跟练完成率 ${display(habits.obj('training')['completion_pct'], 1)}% · 部分完成 ${habits.obj('training')['partial_sessions']} 次',
                  ),
                  note('今天尚未结束，不纳入完成率；少于 3 个有效样本时不显示比例。'),
                ],
              ),
            ),
            action(
              '导出本期 PDF 报告',
              () => runTask(context, () async {
                if (!await confirm(
                  context,
                  '导出健康报告？',
                  'PDF 包含身体、饮食和运动信息，请选择可信保存位置。',
                )) {
                  return;
                }
                final bytes = await app.api.report(period, range.end);
                await app.device.saveFile(
                  'NutriPulse-$period-${range.end}.pdf',
                  bytes,
                  'application/pdf',
                );
              }),
              color: P.cyan,
            ),
          ],
        );
      },
    );
  }
}

Widget legend(String name, Color color) => Row(
  mainAxisSize: MainAxisSize.min,
  children: [
    Container(
      width: 8,
      height: 8,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    ),
    const SizedBox(width: 4),
    Text(name, style: const TextStyle(color: P.muted, fontSize: 10)),
  ],
);
Future<void> detailSheet(
  BuildContext context,
  List<Json> series,
) => showModalBottomSheet(
  context: context,
  isScrollControlled: true,
  useSafeArea: true,
  builder: (c) => SizedBox(
    height: MediaQuery.sizeOf(c).height * .7,
    child: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        title('能量明细'),
        for (final point in series)
          Panel(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                section(point.s('period')),
                Text(
                  '摄入 ${display(point['intake_kcal'])} kcal\n总消耗 ${display(point['expenditure_kcal'])} kcal\n净差 ${display(point['net_kcal'])} kcal\nBMR ${display(point['bmr_kcal'])} kcal · TDEE ${display(point['tdee_kcal'])} kcal',
                ),
                note(
                  '已记录 ${point['logged_days']} 天 · 有目标 ${point['target_days']} 天',
                ),
              ],
            ),
          ),
      ],
    ),
  ),
);
