import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import '../../core/api.dart';
import '../../core/app_scope.dart';
import '../../core/data.dart';
import '../../ui/design.dart';
import '../../ui/forms.dart';
import 'workout_editor.dart';

class FitnessPage extends StatefulWidget {
  const FitnessPage({super.key});
  @override
  State<FitnessPage> createState() => _FitnessPageState();
}

class _FitnessPageState extends State<FitnessPage> {
  bool filtered = false;
  int filterRevision = 0;
  Timer? ticker;
  @override
  void initState() {
    super.initState();
    ticker = Timer.periodic(const Duration(minutes: 1), (_) => tick());
  }

  Future<void> tick() async {
    final app = AppScope.of(context);
    if (app.tab != 1 ||
        WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed ||
        app.syncing ||
        app.deleting) {
      return;
    }
    if (await app.device.read('health_auto_sync') != 'true' || !mounted) return;
    await runTask(context, () => app.syncHealth(requestPermission: false));
  }

  @override
  void dispose() {
    ticker?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context), day = today();
    return RemoteData<List<Json>>(
      revision: app.revision + filterRevision,
      errorBuilder: (error) => PageBody(
        children: [
          title('今日训练', subtitle: '电脑服务未连接'),
          Panel(
            child: Column(
              children: [Text(error.toString()), action('重新连接', app.refresh)],
            ),
          ),
          const PendingBanner('workout'),
          banner(
            '记录运动',
            '保存失败时保留原请求，恢复连接后重试',
            Icons.add_circle_outline,
            () => cardioSheet(context),
            color: P.red,
          ),
          action('记录力量训练', () => strengthSheet(context), color: P.red),
        ],
      ),
      load: () async {
        final profile = await app.api.get('/profile');
        final level = profile.obj('training').s('level');
        final filters = filtered
            ? '?level=${level == 'recovery' || level.isEmpty ? 'beginner' : level}${profile.obj('goal').isEmpty ? '' : '&goal_type=${profile.obj('goal')['goal_type']}'}'
            : '';
        return Future.wait([
          app.api.get('/fitness/days/$day'),
          app.api.get('/training-plans$filters'),
          app.api.get('/devices/conflicts'),
        ]);
      },
      builder: (data) {
        final summary = data[0].obj('summary'),
            plan = data[0].obj('active_plan');
        return PageBody(
          refresh: () async => app.refresh(),
          children: [
            title(
              '今日训练',
              subtitle: 'FITNESS HUB · 做训练，看容量',
              trailing: pill(
                '${userToday().month}月${userToday().day}日',
                color: P.red,
                background: const Color(0xFFFFEEEE),
              ),
            ),
            const PendingBanner('workout'),
            Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  section(
                    '活动能量',
                    trailing: pill(
                      '目标 ${display(summary['activity_goal_kcal'])} kcal',
                      color: P.red,
                      background: const Color(0xFFFFEEEE),
                    ),
                  ),
                  Text(
                    '${display(summary.obj('energy')['activity_kcal'])} kcal',
                    style: const TextStyle(
                      fontSize: 35,
                      fontWeight: FontWeight.w800,
                      color: P.red,
                    ),
                  ),
                  const SizedBox(height: 10),
                  LinearProgressIndicator(
                    value: summary.n('activity_goal_kcal') > 0
                        ? (summary.obj('energy').n('activity_kcal') /
                                  summary.n('activity_goal_kcal'))
                              .clamp(0, 1)
                        : 0,
                    color: P.red,
                    backgroundColor: const Color(0xFFFFEEEE),
                    minHeight: 8,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  const SizedBox(height: 22),
                  Row(
                    children: [
                      Expanded(
                        child: metric('训练分钟', summary['workout_minutes']),
                      ),
                      Expanded(
                        child: metric(
                          '实时心率 bpm',
                          summary['heart_rate_bpm'],
                          color: P.red,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 18),
                  Row(
                    children: [
                      Expanded(
                        child: metric(
                          '设备步数',
                          summary['steps_source'] == null
                              ? null
                              : summary['steps'],
                        ),
                      ),
                      Expanded(
                        child: metric(
                          '训练容量 kg',
                          summary['training_volume'],
                          color: P.blue,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: const Text(
                      '查看数据来源',
                      style: TextStyle(fontSize: 12, color: P.muted),
                    ),
                    children: [
                      note(
                        '手工估算 ${display(summary['manual_activity_kcal'])} kcal · 设备 ${display(summary['device_activity_kcal'])} kcal\n来源 ${summary['activity_source']} · 最近同步 ${summary['activity_synced_at'] ?? '--'}\n力量估算 ${display(summary['strength_kcal'])} kcal · 心率采样 ${summary['heart_rate_sampled_at'] ?? '--'}',
                      ),
                    ],
                  ),
                ],
              ),
            ),
            banner(
              '记录一次运动',
              '选择项目与运动量，保存前可预估消耗',
              Icons.add_circle_outline,
              () => cardioSheet(context),
              color: P.red,
            ),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                pill(
                  '力量组数记录',
                  color: P.red,
                  background: const Color(0xFFFFEEEE),
                  onTap: () => strengthSheet(context),
                ),
                pill(
                  '设备同步',
                  color: P.cyan,
                  onTap: () => runTask(context, app.syncHealth),
                ),
                pill(
                  '消耗试算',
                  color: P.blue,
                  onTap: () => estimateSheet(context),
                ),
              ],
            ),
            const SizedBox(height: 14),
            if (data[2].rows('items').isNotEmpty)
              Panel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    section(
                      '设备与手工记录重叠',
                      trailing: const Icon(Icons.compare_arrows, color: P.red),
                    ),
                    for (final conflict in data[2].rows('items'))
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(
                          '${conflict['local_date']} · ${display(conflict['overlap_seconds'])}秒重叠',
                        ),
                        subtitle: Text(
                          '${conflict['device_start_at'] ?? conflict['start_at']}',
                        ),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () => conflictSheet(context, conflict),
                      ),
                  ],
                ),
              ),
            if (plan.isNotEmpty)
              Panel(
                color: P.softGreen,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    section(plan.s('name')),
                    note(
                      '第 ${plan.obj('progress')['current_week']} 周 · 完整完成 ${plan.obj('progress')['completed']} / ${plan.obj('progress')['total']} · 部分完成 ${plan.obj('progress')['partial']}',
                    ),
                    for (final s in plan.rows('week_sessions'))
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(s.s('title')),
                        subtitle: Text(
                          '${s['scheduled_date']} · ${s['status']}',
                        ),
                        trailing:
                            s['scheduled_date'] == day &&
                                s['status'] == 'SCHEDULED'
                            ? const Icon(
                                Icons.play_circle_outline,
                                color: P.green,
                              )
                            : null,
                        onTap: () => sessionSheet(context, s),
                      ),
                    TextButton(
                      onPressed: () => runTask(context, () async {
                        if (await confirm(
                          context,
                          '停止当前计划？',
                          '已完成的训练保留，停止后不再安排跟练。',
                        )) {
                          await app.api.post('/training-plans/active/stop');
                          app.refresh();
                        }
                      }),
                      child: const Text('停止当前跟练'),
                    ),
                  ],
                ),
              ),
            section('训练账本'),
            if (data[0].rows('workouts').isEmpty)
              Panel(child: note('今天还没有运动记录。')),
            for (final workout in data[0].rows('workouts'))
              Panel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    section(
                      workout['custom_name'] ??
                          workoutNames[workout['workout_type']] ??
                          workout.s('workout_type'),
                      trailing: pill(
                        '${display(workout['kcal'])} kcal',
                        color: P.red,
                        background: const Color(0xFFFFEEEE),
                      ),
                    ),
                    note(
                      '${display(workout['minutes'])} 分钟 · 来源 ${workout['kcal_source']} · ${workout['calculation_version']}',
                    ),
                    for (final s in workout.rows('sets'))
                      note(
                        '${s['exercise_name']} · ${s['duration_sec'] != null ? '${s['duration_sec']}秒' : '${s['reps']}次'} · ${s['weight_kg'] == null ? '自重' : '${s['weight_kg']}kg'} · ${s['completed_at'] == null ? '未完成' : '完成'}',
                      ),
                    TextButton(
                      onPressed: () => runTask(
                        context,
                        () => recoverySheet(context, workout.s('id')),
                      ),
                      child: const Text('训练后营养与恢复建议'),
                    ),
                  ],
                ),
              ),
            section(
              '官方推荐计划',
              trailing: pill(
                filtered ? '查看全部' : '只看适合我的',
                onTap: () => setState(() {
                  filtered = !filtered;
                  filterRevision++;
                }),
              ),
            ),
            if (filtered) note('按个人训练水平和阶段目标筛选；恢复水平使用初级训练筛选。'),
            if (data[1].rows('items').isEmpty)
              Panel(child: note('当前条件没有计划，可切回全部查看。')),
            for (final item in data[1].rows('items'))
              Panel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    section(item.s('name')),
                    note(
                      '${item['level']} · ${item['weeks']} 周 · 每周 ${item['days_per_week']} 天',
                    ),
                    Text(item.s('description')),
                    const SizedBox(height: 8),
                    action(
                      '查看计划详情',
                      () => planSheet(context, item),
                      color: P.red,
                    ),
                  ],
                ),
              ),
          ],
        );
      },
    );
  }
}

Future<void> estimateSheet(BuildContext context) async {
  final app = AppScope.of(context);
  await editSheet(
    context,
    '运动消耗试算',
    [
      const Field(
        'workout_type',
        '运动项目',
        choices: {
          'walking': '步行',
          'running': '跑步',
          'cycling': '骑行',
          'swimming': '游泳',
          'strength': '力量',
          'yoga': '瑜伽',
        },
      ),
      const Field(
        'intensity',
        '强度',
        value: 'moderate',
        choices: {'low': '低', 'moderate': '中', 'high': '高'},
      ),
      const Field(
        'minutes',
        '持续分钟',
        value: 30,
        required: true,
        numeric: true,
        min: 1,
        max: 1440,
      ),
    ],
    (body) async {
      final result = await app.api.post('/workouts/estimate', body);
      if (context.mounted) {
        await confirm(
          context,
          '估算消耗 ${display(result['kcal'])} kcal',
          '体重 ${display(result['weight_kg'], 1)}kg · ${result['weight_source']}\nMET ${result['met_value']} · ${result['calculation_version']}\n这是试算，还没有写入训练账本。',
          label: '知道了',
        );
      }
    },
    button: '计算消耗',
  );
}

Future<void> cardioSheet(BuildContext context, {Json? session}) async {
  final app = AppScope.of(context);
  PendingWrite? pending;
  Json? saved;
  final ok = await editSheet(
    context,
    session == null ? '记录运动' : session.s('title'),
    [
      const Field('workout_type', '运动项目', choices: workoutNames),
      const Field(
        'intensity',
        '强度',
        value: 'moderate',
        choices: {'low': '低', 'moderate': '中', 'high': '高'},
      ),
      Field(
        'minutes',
        '实际运动分钟',
        value: session?['minimum_duration_minutes'] ?? 30,
        numeric: true,
        required: true,
        min: 1,
        max: 1440,
      ),
      const Field(
        'kcal',
        '消耗 kcal（可空，自动按 MET 计算）',
        numeric: true,
        min: 0,
        max: 10000,
      ),
      const Field('custom_name', '自定义运动名称（自定义项目必填）'),
    ],
    (body) async {
      if (body['workout_type'] == 'custom' &&
          (body['custom_name'] == null || body['kcal'] == null)) {
        throw ApiException('自定义运动需要填写名称和消耗热量');
      }
      final payload = {
        ...body,
        'local_date': session?['scheduled_date'] ?? today(),
        if (session != null) 'plan_session_id': session['id'],
      }..removeWhere((key, value) => value == null);
      pending ??= PendingWrite('/workouts', payload);
      saved = await persistAndSend(app, 'workout', pending!);
    },
    freeze: true,
    introduction: note('已登记项目留空热量时使用体重与 MET 估算；可先在健身页试算。计划未达到规定时长会保存为部分完成。'),
  );
  if (ok && context.mounted && saved != null) {
    await runTask(context, () => recoverySheet(context, saved!.s('id')));
  }
}

Future<void> recoverySheet(BuildContext context, String id) async {
  final app = AppScope.of(context),
      data = await AppScope.of(context).api.get('/workouts/$id/recovery');
  if (!context.mounted) return;
  await showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (c) => Padding(
      padding: const EdgeInsets.all(22),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            title('训练后的营养修复'),
            note('来源 ${data['source']}'),
            for (final a in data.rows('advice'))
              Panel(child: Text(a.s('text'))),
            for (final n in (data['notices'] as List?) ?? [])
              note(n.toString()),
            action('去看看吃什么', () {
              Navigator.pop(c);
              app.navigate(2);
            }),
          ],
        ),
      ),
    ),
  );
}

Future<void> planSheet(BuildContext context, Json plan) async {
  final app = AppScope.of(context);
  await showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (c) => Padding(
      padding: const EdgeInsets.all(22),
      child: SizedBox(
        height: MediaQuery.sizeOf(c).height * .8,
        child: Column(
          children: [
            title(plan.s('name')),
            Expanded(
              child: ListView(
                children: [
                  for (final key in [
                    'description',
                    'suitability',
                    'contraindications',
                    'warmup',
                    'cooldown',
                    'progression_rule',
                    'completion_rule',
                  ])
                    if (plan[key] != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Text(
                          '${{'suitability': '适用人群', 'contraindications': '训练提示', 'warmup': '热身', 'cooldown': '冷身', 'progression_rule': '进阶规则', 'completion_rule': '完成标准'}[key] ?? ''}\n${plan[key]}',
                        ),
                      ),
                  for (final d in plan.rows('days'))
                    Panel(
                      color: P.background,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '第 ${d['day_no']} 天 · ${d['title']}',
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                          for (final e
                              in (jsonDecode(d.s('session_template_json'))
                                  as List))
                            note(e.toString()),
                        ],
                      ),
                    ),
                  if (plan['alternatives'] != null)
                    note('替代动作：${plan['alternatives']}'),
                ],
              ),
            ),
            action(
              '选择此计划并开始跟练',
              () => runTask(context, () async {
                if (!await confirm(
                  context,
                  '启用这套计划？',
                  '从今天开始安排训练；如果已有计划，将停止旧计划，历史记录保留。',
                )) {
                  return;
                }
                await app.api.post('/training-plans/${plan['id']}/enroll', {
                  'start_date': today(),
                });
                app.refresh();
                if (c.mounted) Navigator.pop(c);
              }),
              color: P.red,
            ),
          ],
        ),
      ),
    ),
  );
}

Future<void> sessionSheet(BuildContext context, Json session) async {
  final app = AppScope.of(context);
  await showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (c) => Padding(
      padding: const EdgeInsets.all(22),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            title(
              session.s('title'),
              subtitle: '${session['scheduled_date']} · ${session['status']}',
            ),
            for (var i = 0; i < (session['exercises'] as List).length; i++)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(session['exercises'][i].toString()),
                trailing: session['status'] == 'SCHEDULED'
                    ? IconButton(
                        icon: const Icon(Icons.edit_outlined, size: 18),
                        onPressed: () => editSheet(
                          context,
                          '替换动作',
                          [
                            const Field(
                              'replacement',
                              '替代动作（含组次）',
                              required: true,
                            ),
                            const Field('reason', '替换原因（至少2字）', required: true),
                          ],
                          (body) async {
                            if ((body['reason'] as String).length < 2) {
                              throw ApiException('请填写至少2字的原因');
                            }
                            await app.api.post(
                              '/training-plans/active/sessions/${session['id']}/replace',
                              {...body, 'index': i},
                            );
                            app.refresh();
                            if (c.mounted) Navigator.pop(c);
                          },
                        ),
                      )
                    : null,
              ),
            if (session['status'] == 'SCHEDULED' &&
                session['scheduled_date'] == today())
              action('开始记录本次训练', () {
                Navigator.pop(c);
                if (session['minimum_duration_minutes'] != null) {
                  cardioSheet(context, session: session);
                } else {
                  strengthSheet(context, session: session);
                }
              }, color: P.red),
          ],
        ),
      ),
    ),
  );
}

Future<void> conflictSheet(BuildContext context, Json conflict) async {
  final app = AppScope.of(context);
  await editSheet(
    context,
    '处理运动数据重叠',
    [
      const Field(
        'resolution',
        '采用方式',
        choices: {
          'KEEP_DEVICE': '采用设备',
          'KEEP_MANUAL': '采用手工',
          'MERGE_NON_OVERLAPPING': '只合并不重叠部分',
        },
      ),
    ],
    (body) async {
      await app.api.post('/devices/conflicts/${conflict['id']}/resolve', body);
      app.refresh();
    },
    introduction: note(
      '重叠 ${display(conflict['overlap_seconds'])}秒。处置会重新计算活动消耗，原始账本保留。',
    ),
  );
}
