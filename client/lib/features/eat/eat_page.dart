import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';
import '../../core/app_scope.dart';
import '../../core/data.dart';
import '../../ui/design.dart';
import '../../ui/forms.dart';
import 'chat_page.dart';

class EatPage extends StatefulWidget {
  const EatPage({super.key});
  @override
  State<EatPage> createState() => _EatPageState();
}

class _EatPageState extends State<EatPage> {
  String meal = 'lunch', scenario = 'self_cook', pageDay = today();
  bool busy = false;
  bool scenarioTouched = false;
  int seenRevision = -1;
  Json? recommendations;
  String? error;
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final revision = AppScope.of(context).revision;
    if (revision != seenRevision) {
      recommendations = null;
      error = null;
      seenRevision = revision;
    }
  }

  Future<List<Json>> loadBudget(AppController app) async {
    final data = await Future.wait([
      app.api.get('/analytics/days?date=${today()}'),
      app.api.get('/profile'),
    ]);
    if (!scenarioTouched) {
      scenario = data[1].obj('dining').s('preferred_scenario');
    }
    return data;
  }

  Future<void> recommend({bool shuffle = false, String? avoid}) async {
    final app = AppScope.of(context);
    if (pageDay != today()) {
      setState(() {
        pageDay = today();
        recommendations = null;
      });
      app.refresh();
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final data = await app.api.post('/recommendations/meals', {
        'local_date': pageDay,
        'meal_type': meal,
        'scenario': scenario,
        'shuffle': shuffle,
        'avoid_recipe_id': ?avoid,
      });
      if (!mounted) return;
      setState(() => recommendations = data);
      final snapshot = object(
        jsonDecode(data.obj('session').s('context_snapshot_json')),
      );
      if (shuffle && data.rows('items').isNotEmpty) {
        await showDialog(
          context: context,
          builder: (c) => BlindBoxDialog(
            snapshot.obj('blind_box'),
            data.rows('items').first.s('title'),
          ),
        );
      }
    } on Exception catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    return Stack(
      children: [
        RemoteData<List<Json>>(
          revision: app.revision,
          load: () => loadBudget(app),
          builder: (data) => PageBody(
            refresh: () async => app.refresh(),
            children: [
              title('今天，吃点什么？', subtitle: 'WHAT TO EAT · 把纠结交给营养预算'),
              Panel(
                color: P.softGreen,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    section(
                      '今日剩余营养预算',
                      trailing: const Icon(
                        Icons.auto_awesome,
                        color: P.deepGreen,
                      ),
                    ),
                    Text(
                      '${data[0]['has_target'] == true ? display(data[0].obj('energy')['remaining_kcal']) : '--'} kcal',
                      style: const TextStyle(
                        color: P.deepGreen,
                        fontSize: 35,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    note(
                      '${goalNames[data[1].obj('goal').s('goal_type')] ?? '未设阶段目标'} · 结合营养缺口、偏好和过敏忌口推荐',
                    ),
                    note(
                      '蛋白质目标 ${display(data[0].obj('target')['protein_g'])}g · 已摄入 ${display(data[0].obj('macros')['protein_g'], 1)}g',
                    ),
                  ],
                ),
              ),
              Panel(
                child: Column(
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: DropdownButtonFormField<String>(
                            isExpanded: true,
                            initialValue: meal,
                            decoration: const InputDecoration(labelText: '餐次'),
                            items: mealNames.entries
                                .map(
                                  (e) => DropdownMenuItem(
                                    value: e.key,
                                    child: Text(e.value),
                                  ),
                                )
                                .toList(),
                            onChanged: busy
                                ? null
                                : (v) => setState(() {
                                    meal = v!;
                                    recommendations = null;
                                  }),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: DropdownButtonFormField<String>(
                            isExpanded: true,
                            key: ValueKey('scenario-$scenario'),
                            initialValue: scenario,
                            decoration: const InputDecoration(
                              labelText: '用餐场景',
                            ),
                            items: scenarioNames.entries
                                .map(
                                  (e) => DropdownMenuItem(
                                    value: e.key,
                                    child: Text(e.value),
                                  ),
                                )
                                .toList(),
                            onChanged: busy
                                ? null
                                : (v) => setState(() {
                                    scenarioTouched = true;
                                    scenario = v!;
                                    recommendations = null;
                                  }),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    action(
                      busy ? '正在计算推荐…' : '生成我的推荐',
                      busy ? null : recommend,
                    ),
                    const SizedBox(height: 9),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: busy
                            ? null
                            : () => recommend(
                                shuffle: true,
                                avoid: recommendations
                                    ?.rows('items')
                                    .firstOrNull?['candidate_ref_id'],
                              ),
                        icon: const Icon(Icons.casino_outlined),
                        label: const Text('盲盒转盘 · 帮我随机选'),
                      ),
                    ),
                  ],
                ),
              ),
              banner(
                'AI 饮食顾问',
                '多轮聊清需求，确认后再加入饮食计划',
                Icons.forum_outlined,
                () => runTask(context, () => openChat(context)),
              ),
              if (busy) const LinearProgressIndicator(color: P.green),
              if (error != null)
                Panel(
                  child: Text(error!, style: const TextStyle(color: P.red)),
                ),
              section('适合你的方案'),
              if (recommendations == null && !busy)
                Panel(child: note('选择餐次与场景，生成个性化推荐。偏好和过敏限制可在「我的」中修改。')),
              if (recommendations != null) ...[
                note(
                  recommendations!.obj('session')['constraint_version'] ==
                          'agent-v1'
                      ? '联网 Agent 推荐 · 服务端校验限制'
                      : '本地规则推荐 · 来源由电脑服务提供',
                ),
                if (recommendations!.rows('items').isEmpty)
                  Panel(child: note('当前限制条件下没有匹配的安全候选，请调整偏好或手工记录。')),
                for (final item in recommendations!.rows('items'))
                  RecommendationCard(
                    key: ValueKey(item['id']),
                    item: item,
                    day: pageDay,
                    reload: () => recommend(),
                  ),
              ],
              const SizedBox(height: 55),
            ],
          ),
        ),
        Positioned(
          right: 20,
          bottom: 20,
          child: FloatingActionButton(
            tooltip: '召唤 AI 饮食顾问',
            heroTag: 'chat',
            onPressed: () => runTask(context, () => openChat(context)),
            backgroundColor: P.green,
            foregroundColor: Colors.white,
            child: const Icon(Icons.auto_awesome),
          ),
        ),
      ],
    );
  }
}

class RecommendationCard extends StatefulWidget {
  final Json item;
  final String day;
  final Future<void> Function() reload;
  const RecommendationCard({
    super.key,
    required this.item,
    required this.day,
    required this.reload,
  });
  @override
  State<RecommendationCard> createState() => _RecommendationCardState();
}

class _RecommendationCardState extends State<RecommendationCard> {
  double servings = 1;
  bool busy = false;
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context),
        item = widget.item,
        n = item.obj('nutrition');
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          section(
            item.s('title'),
            trailing: pill('匹配 ${display(item['score'])} 分'),
          ),
          note(
            '${item['estimated_cost_cny'] == null ? '价格未知' : '约 ¥${display(item.n('estimated_cost_cny') * servings, 1)}'} · ${display(item.n('prep_minutes') + item.n('cook_minutes'))} 分钟',
          ),
          const SizedBox(height: 5),
          Text(
            '${display(n.n('kcal') * servings)} kcal',
            style: const TextStyle(
              fontSize: 25,
              fontWeight: FontWeight.w800,
              color: P.deepGreen,
            ),
          ),
          note(
            '碳水 ${display(n.n('carb_g') * servings, 1)}g · 蛋白 ${display(n.n('protein_g') * servings, 1)}g · 脂肪 ${display(n.n('fat_g') * servings, 1)}g',
            color: P.blue,
          ),
          DropdownButtonFormField<double>(
            isExpanded: true,
            initialValue: servings,
            decoration: const InputDecoration(labelText: '份量'),
            items: [0.5, 1.0, 1.5, 2.0]
                .map((v) => DropdownMenuItem(value: v, child: Text('$v 份')))
                .toList(),
            onChanged: busy ? null : (v) => setState(() => servings = v!),
          ),
          const SizedBox(height: 9),
          for (final text in (item['reasons'] as List?) ?? [])
            note(text.toString()),
          for (final text in (item['modifications'] as List?) ?? [])
            note('建议：$text'),
          Wrap(
            spacing: 8,
            children: [
              TextButton.icon(
                onPressed: () => runTask(
                  context,
                  () => recipeSheet(
                    context,
                    item.s('candidate_ref_id'),
                    servings,
                  ),
                ),
                icon: const Icon(Icons.menu_book_outlined, size: 17),
                label: const Text('菜谱与食材'),
              ),
              TextButton.icon(
                onPressed: () => feedbackSheet(context, item, widget.reload),
                icon: const Icon(Icons.tune, size: 17),
                label: Text(
                  item['feedback_type'] == null
                      ? '调整推荐'
                      : '已反馈 ${item['feedback_type']}',
                ),
              ),
            ],
          ),
          action(
            busy ? '正在加入…' : '加入今日饮食计划',
            busy
                ? null
                : () async {
                    if (widget.day != today()) {
                      message(context, '日期已变化，请重新生成今天的推荐');
                      return;
                    }
                    setState(() => busy = true);
                    await runTask(context, () async {
                      await app.api.post(
                        '/recommendations/${item['id']}/accept',
                        {'servings': servings},
                      );
                      app.navigate(0);
                      if (context.mounted) message(context, '已加入计划，实际食用后请确认吃过');
                    });
                    if (mounted) setState(() => busy = false);
                  },
          ),
        ],
      ),
    );
  }
}

Future<void> feedbackSheet(
  BuildContext context,
  Json item,
  Future<void> Function() reload,
) async {
  final app = AppScope.of(context);
  await editSheet(
    context,
    '调整后续推荐',
    [
      const Field(
        'feedback_type',
        '反馈',
        choices: {
          'DISLIKE': '不喜欢',
          'REPEATED': '最近吃太多',
          'UNSUITABLE': '不合适',
          'CLEAR': '撤销反馈',
        },
      ),
    ],
    (body) async {
      await app.api.post('/recommendations/${item['id']}/feedback', body);
      await reload();
    },
    introduction: note('反馈影响排序，不会自动修改永久忌口或过敏库。'),
  );
}

Future<void> recipeSheet(
  BuildContext context,
  String id,
  double servings,
) async {
  final recipe = await AppScope.of(context).api.get('/recipes/$id');
  if (!context.mounted) return;
  await showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (c) => Padding(
      padding: const EdgeInsets.all(22),
      child: SizedBox(
        height: MediaQuery.sizeOf(c).height * .8,
        child: ListView(
          children: [
            title(recipe.s('name'), subtitle: '$servings 份 · 按标准份缩放食材'),
            if (recipe['matches_current_restrictions'] != true)
              note('与最新饮食限制冲突，请重新推荐', color: P.red),
            for (final i in recipe.rows('ingredients'))
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(i.s('name')),
                trailing: Text('${display(i.n('grams') * servings, 1)}g'),
              ),
            section('烹饪步骤'),
            for (var i = 0; i < (recipe['instructions'] as List).length; i++)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text('${i + 1}. ${recipe['instructions'][i]}'),
              ),
            section('可选食材替代'),
            for (final s in recipe.rows('substitutions'))
              Panel(
                color: P.background,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${s['original_name']} → ${s['replacement_name']} ${display(s.n('grams_per_serving') * servings, 1)}g',
                    ),
                    note(
                      '替换后整餐约 ${display(s.obj('nutrition_per_serving_if_used').n('kcal') * servings)} kcal · 蛋白 ${display(s.obj('nutrition_per_serving_if_used').n('protein_g') * servings, 1)}g',
                    ),
                  ],
                ),
              ),
            note('食材替代仅供备餐参考，不会自动改写预记餐食。实际替换后请到饮食页编辑明细。'),
            note(
              '估算价格 ${recipe['estimated_cost_cny'] == null ? '未知' : '¥${display(recipe.n('estimated_cost_cny') * servings, 1)}'} · 过敏原 ${(recipe['allergens'] as List).join('、')}',
            ),
          ],
        ),
      ),
    ),
  );
}

class BlindBoxDialog extends StatelessWidget {
  final Json box;
  final String selected;
  const BlindBoxDialog(this.box, this.selected, {super.key});
  @override
  Widget build(BuildContext context) {
    final pool = box.rows('candidate_pool');
    return AlertDialog(
      title: const Text('今天的饮食盲盒'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: pi * 8),
            duration: const Duration(milliseconds: 1800),
            curve: Curves.easeOutCubic,
            builder: (_, angle, child) =>
                Transform.rotate(angle: angle, child: child),
            child: SizedBox(
              width: 220,
              height: 220,
              child: CustomPaint(painter: WheelPainter(pool)),
            ),
          ),
          const SizedBox(height: 15),
          Text(
            '抽中：$selected',
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          note('来自 ${box['candidate_count']} 道已通过限制校验的候选'),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('查看方案'),
        ),
      ],
    );
  }
}

class WheelPainter extends CustomPainter {
  final List<Json> items;
  WheelPainter(this.items);
  @override
  void paint(Canvas canvas, Size size) {
    if (items.isEmpty) return;
    final center = size.center(Offset.zero), radius = size.width / 2;
    for (var i = 0; i < items.length; i++) {
      final start = 2 * pi * i / items.length, sweep = 2 * pi / items.length;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        start,
        sweep,
        true,
        Paint()..color = [P.green, P.cyan, P.blue, P.yellow][i % 4],
      );
      canvas.save();
      canvas.translate(center.dx, center.dy);
      canvas.rotate(start + sweep / 2);
      final text = TextPainter(
        text: TextSpan(
          text: (items[i]['title'] ?? items[i]['name'] ?? items[i]['recipe_id'])
              .toString(),
          style: const TextStyle(color: Colors.white, fontSize: 10),
        ),
        maxLines: 1,
        ellipsis: '…',
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: radius - 16);
      text.paint(canvas, Offset(14, -text.height / 2));
      canvas.restore();
    }
    canvas.drawCircle(center, 20, Paint()..color = Colors.white);
  }

  @override
  bool shouldRepaint(covariant WheelPainter old) => old.items != items;
}
