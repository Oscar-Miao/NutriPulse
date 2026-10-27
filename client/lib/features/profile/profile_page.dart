import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import '../../core/api.dart';
import '../../core/app_scope.dart';
import '../../core/data.dart';
import '../../ui/design.dart';
import '../../ui/forms.dart';

const activityNames = {
  'sedentary': '久坐',
  'light': '轻度活动',
  'moderate': '中等活动',
  'high': '高活动',
  'very_high': '极高活动',
};
const levelNames = {
  'beginner': '初学',
  'intermediate': '进阶',
  'advanced': '高阶',
  'recovery': '恢复期',
};

class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key});
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    return RemoteData<Json>(
      revision: app.revision,
      load: () => app.api.get('/profile'),
      builder: (data) {
        final p = data.obj('profile'),
            m = data.obj('measurement'),
            t = data.obj('target'),
            training = data.obj('training');
        return PageBody(
          refresh: () async => app.refresh(),
          children: [
            title('个人中心', subtitle: 'PROFILE HUB · 让每一个目标更懂你'),
            Panel(
              color: P.softGreen,
              child: Row(
                children: [
                  const CircleAvatar(
                    radius: 29,
                    backgroundColor: P.green,
                    child: Icon(
                      Icons.person_rounded,
                      color: Colors.white,
                      size: 34,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          p.s('display_name'),
                          style: const TextStyle(
                            fontSize: 21,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        note(
                          '${goalNames[data.obj('goal').s('goal_type')] ?? '尚未设置目标'} · ${levelNames[training.s('level')] ?? '未设置训练水平'}',
                        ),
                      ],
                    ),
                  ),
                  const Icon(Icons.verified_rounded, color: P.green),
                ],
              ),
            ),
            Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  section(
                    '身体基础信息',
                    trailing: pill(
                      '编辑',
                      onTap: () => editProfile(context, data),
                    ),
                  ),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      Expanded(child: metric('身高', p['height_cm'], unit: 'cm')),
                      Expanded(
                        child: metric(
                          '体重',
                          m['weight_kg'],
                          unit: 'kg',
                          digits: 1,
                        ),
                      ),
                      Expanded(
                        child: metric(
                          '体脂率',
                          m['body_fat_pct'],
                          unit: '%',
                          digits: 1,
                        ),
                      ),
                    ],
                  ),
                  note(
                    '出生日期 ${p['birth_date'] ?? '未填写'} · ${activityNames[p.s('activity_level')] ?? ''}',
                  ),
                  action('记录新的体重 / 体脂', () => measurementSheet(context)),
                ],
              ),
            ),
            section('阶段目标'),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: goalNames.entries
                  .map(
                    (e) => SizedBox(
                      width: (MediaQuery.sizeOf(context).width - 48) / 2,
                      child: Panel(
                        color: data.obj('goal').s('goal_type') == e.key
                            ? P.softGreen
                            : Colors.white,
                        child: InkWell(
                          onTap: () => runTask(
                            context,
                            () => previewGoal(context, e.key),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Icon(
                                e.key == 'muscle_gain'
                                    ? Icons.fitness_center
                                    : e.key == 'fat_loss'
                                    ? Icons.local_fire_department_outlined
                                    : Icons.favorite_outline,
                                color: P.deepGreen,
                              ),
                              const SizedBox(height: 7),
                              Text(
                                e.value,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              note(
                                e.key == 'fat_loss'
                                    ? '管理热量赤字'
                                    : e.key == 'muscle_gain'
                                    ? '支持训练与盈余'
                                    : e.key == 'recovery'
                                    ? '以恢复节奏为先'
                                    : '保持长期平衡',
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  )
                  .toList(),
            ),
            Panel(
              color: const Color(0xFF18392C),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '你的代谢与每日目标',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 18),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      Expanded(
                        child: metric(
                          'BMR · kcal',
                          t['bmr_kcal'],
                          color: P.green,
                        ),
                      ),
                      Expanded(
                        child: metric(
                          'TDEE · kcal',
                          t['tdee_kcal'],
                          color: P.green,
                        ),
                      ),
                      Expanded(
                        child: metric('饮水 · ml', t['water_ml'], color: P.cyan),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Text(
                    '每日摄入 ${display(t['kcal'])} kcal',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  note(
                    '碳水 ${display(t['carb_g'])}g · 蛋白 ${display(t['protein_g'])}g · 脂肪 ${display(t['fat_g'])}g',
                    color: Colors.white70,
                  ),
                  note(
                    t.isEmpty
                        ? '完善身体信息、测量并选择目标后生成'
                        : '算法 ${t['algorithm_version'] ?? '服务端计算'} · 生效 ${t['effective_from']}',
                    color: Colors.white60,
                  ),
                ],
              ),
            ),
            Panel(
              child: Column(
                children: [
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.restaurant_menu, color: P.green),
                    title: const Text('饮食偏好与过敏忌口'),
                    subtitle: Text(
                      '过敏原 ${((data['allergies'] as List?) ?? []).length} 项 · ${scenarioNames[data.obj('dining').s('preferred_scenario')] ?? '自己下厨'}',
                    ),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => preferencesSheet(context, data),
                  ),
                  const Divider(color: P.line),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.fitness_center, color: P.red),
                    title: const Text('训练偏好与动作限制'),
                    subtitle: Text(
                      '${training['days_per_week'] ?? '--'} 天 / 周 · ${training['session_minutes'] ?? '--'} 分钟 / 次',
                    ),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => trainingSheet(context, training),
                  ),
                ],
              ),
            ),
            Panel(
              child: Column(
                children: [
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.watch_outlined, color: P.cyan),
                    title: const Text('运动设备与同步'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const DevicesPage()),
                    ),
                  ),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.lock_outline, color: P.blue),
                    title: const Text('个人数据与隐私'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => privacySheet(context),
                  ),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.wifi, color: P.green),
                    title: const Text('本地电脑连接'),
                    subtitle: Text(app.api.baseUrl),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => connectionSheet(context),
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

Future<void> editProfile(BuildContext context, Json data) async {
  final app = AppScope.of(context), p = data.obj('profile');
  await editSheet(
    context,
    '身体基础信息',
    [
      Field('display_name', '昵称', value: p['display_name'], required: true),
      Field('birth_date', '出生日期 YYYY-MM-DD', value: p['birth_date']),
      Field(
        'formula_sex',
        '代谢公式使用的性别',
        value: p['formula_sex'],
        choices: const {'male': '男性公式', 'female': '女性公式'},
      ),
      Field(
        'height_cm',
        '身高 cm',
        value: p['height_cm'],
        numeric: true,
        min: 100,
        max: 230,
      ),
      Field(
        'activity_level',
        '日常活动等级',
        value: p['activity_level'],
        choices: activityNames,
      ),
    ],
    (body) async {
      if (body['birth_date'] != null &&
          (DateTime.tryParse(body['birth_date']) == null ||
              dayString(DateTime.parse(body['birth_date'])) !=
                  body['birth_date'])) {
        throw ApiException('出生日期请按 YYYY-MM-DD 填写');
      }
      await app.api.put('/profile', body);
      app.refresh();
    },
  );
}

Future<void> measurementSheet(BuildContext context) async {
  final app = AppScope.of(context);
  await editSheet(
    context,
    '记录身体测量',
    [
      const Field(
        'weight_kg',
        '体重 kg',
        required: true,
        numeric: true,
        min: 25,
        max: 350,
      ),
      const Field(
        'body_fat_pct',
        '体脂率 %（可留空）',
        numeric: true,
        min: 0,
        max: 100,
      ),
    ],
    (body) async {
      await app.api.post('/measurements', body);
      app.refresh();
    },
  );
}

Future<void> previewGoal(BuildContext context, String goal) async {
  final app = AppScope.of(context),
      preview = await AppScope.of(
        context,
      ).api.post('/goals/preview', {'goal_type': goal});
  if (!context.mounted) return;
  final target = preview.obj('proposed_target');
  final content = target.isEmpty
      ? '还缺少：${(preview['missing_fields'] as List).join('、')}。\n${preview['can_activate'] == true ? '可先选择阶段，补齐资料后生成目标。' : '请先补齐资料。'}'
      : '当前目标 ${display(preview.obj('current_target')['kcal'])} kcal\n拟议目标 ${display(target['target_kcal'])} kcal\n碳水 ${display(target['carb_g'])}g · 蛋白 ${display(target['protein_g'])}g · 脂肪 ${display(target['fat_g'])}g\n基于最新身体资料计算，确认后生效。';
  if (preview['can_activate'] == true &&
      await confirm(context, '切换到${goalNames[goal]}？', content)) {
    await app.api.post('/goals', {
      'goal_type': goal,
      'preview_fingerprint': preview['input_fingerprint'],
    });
    app.refresh();
  } else if (preview['can_activate'] != true && context.mounted) {
    message(context, content);
  }
}

Future<void> preferencesSheet(BuildContext context, Json data) async {
  final app = AppScope.of(context), d = data.obj('dining');
  await editSheet(
    context,
    '饮食偏好与限制',
    [
      Field(
        'allergies',
        '过敏原：花生、鸡蛋、牛奶、大豆、鱼、虾蟹、坚果、小麦、芝麻',
        value: (data['allergies'] as List).join('，'),
        multiline: true,
      ),
      Field(
        'restrictions',
        '忌口 / 食材关键词，逗号分隔',
        value: (data['restrictions'] as List).join('，'),
      ),
      Field(
        'flavors',
        '口味：清淡、咸鲜、甜口、香辣，逗号分隔',
        value: ((d['flavors'] as List?) ?? []).join('，'),
      ),
      Field(
        'preferred_scenario',
        '默认用餐场景',
        value: d['preferred_scenario'],
        choices: scenarioNames,
      ),
      Field(
        'max_cost_cny',
        '单餐预算 ¥（可留空）',
        value: d['max_cost_cny'],
        numeric: true,
        min: 1,
        max: 1000,
      ),
      Field(
        'max_cook_minutes',
        '最长烹饪分钟（可留空）',
        value: d['max_cook_minutes'],
        numeric: true,
        integer: true,
        min: 5,
        max: 240,
      ),
    ],
    (body) async {
      await app.api.put('/preferences', {
        'allergies': words(body['allergies'] ?? ''),
        'restrictions': words(body['restrictions'] ?? ''),
        'preferences': data['preferences'],
        'dining': {
          'flavors': words(body['flavors'] ?? ''),
          'preferred_scenario': body['preferred_scenario'],
          'max_cost_cny': body['max_cost_cny'],
          'max_cook_minutes': body['max_cook_minutes'],
        },
      });
      app.refresh();
    },
    introduction: note('过敏原使用服务端支持的名称或代码；推荐仍需核对餐厅真实配料。'),
  );
}

Future<void> trainingSheet(BuildContext context, Json data) async {
  final app = AppScope.of(context);
  await editSheet(
    context,
    '训练偏好与限制',
    [
      Field('level', '训练水平', value: data['level'], choices: levelNames),
      Field(
        'days_per_week',
        '每周天数',
        value: data['days_per_week'] ?? 3,
        numeric: true,
        integer: true,
        required: true,
        min: 1,
        max: 7,
      ),
      Field(
        'session_minutes',
        '每次分钟数',
        value: data['session_minutes'] ?? 45,
        numeric: true,
        integer: true,
        required: true,
        min: 10,
        max: 240,
      ),
      Field(
        'active_kcal_goal',
        '每日活动目标 kcal',
        value: data['active_kcal_goal'] ?? 300,
        numeric: true,
        integer: true,
        required: true,
        min: 50,
        max: 2000,
      ),
      Field(
        'equipment',
        '可用器械，逗号分隔',
        value: ((data['equipment'] as List?) ?? []).join('，'),
      ),
      Field(
        'limitations',
        '动作限制，逗号分隔',
        value: ((data['limitations'] as List?) ?? []).join('，'),
      ),
    ],
    (body) async {
      body['equipment'] = words(body['equipment'] ?? '');
      body['limitations'] = words(body['limitations'] ?? '');
      await app.api.put('/training-profile', body);
      app.refresh();
    },
  );
}

Future<void> connectionSheet(BuildContext context) async {
  final app = AppScope.of(context);
  await editSheet(
    context,
    '连接本地电脑',
    [
      Field('url', '服务地址', value: app.api.baseUrl, required: true),
      const Field('code', '一次性配对码（模拟器直连可留空）'),
      const Field('token', '手动访问令牌（可留空）', obscure: true),
    ],
    (body) async {
      final url = (body['url'] as String).replaceAll(RegExp(r'/+$'), '');
      if (!safeServerUrl(url)) {
        throw ApiException('地址须为 HTTPS 或本机 / 局域网 HTTP，不能带路径、账号或参数');
      }
      var token =
          body['token'] as String? ??
          (url == app.api.baseUrl ? app.api.token : '');
      if (body['code'] != null) {
        final pairing = ApiClient(baseUrl: url);
        try {
          final response = await pairing.post('/auth/pair', {
            'code': body['code'],
          });
          token = response.s('access_token');
          if (token.isEmpty) throw ApiException('配对响应缺少访问凭据');
        } finally {
          pairing.close();
        }
      }
      await app.device.configure(url, token);
      app.api.baseUrl = url;
      app.api.token = token;
      app.refresh();
    },
    introduction: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        note('模拟器：10.0.2.2:8787；真机：电脑局域网地址。先在电脑运行 server/run.py。'),
        TextButton(
          onPressed: () => runTask(context, () async {
            await app.device.configure(app.api.baseUrl, '');
            app.api.token = '';
            app.refresh();
            if (context.mounted) message(context, '本机凭据已清除');
          }),
          child: const Text('清除已保存的访问凭据'),
        ),
      ],
    ),
  );
}

class DevicesPage extends StatelessWidget {
  const DevicesPage({super.key});
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('运动设备')),
      body: RemoteData<Json>(
        revision: app.revision,
        load: () => app.api.get('/devices'),
        builder: (data) => PageBody(
          children: [
            banner(
              '连接 Health Connect',
              '读取活动热量、步数、心率、体重和体脂',
              Icons.watch,
              () => runTask(context, app.syncHealth),
              color: P.cyan,
            ),
            for (final d in data.rows('items'))
              Panel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    section(d.s('provider')),
                    note('${d['status']} · ${d['sample_count']} 条样本'),
                    note('最近同步 ${d['last_synced_at'] ?? '尚未同步'}'),
                    Wrap(
                      spacing: 8,
                      children: [
                        pill(
                          '停止同步，保留历史',
                          onTap: () => runTask(
                            context,
                            () => disconnect(context, d, false),
                          ),
                        ),
                        pill(
                          '删除设备历史',
                          color: P.red,
                          onTap: () => runTask(
                            context,
                            () => disconnect(context, d, true),
                          ),
                        ),
                      ],
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

Future<void> disconnect(BuildContext context, Json device, bool delete) async {
  final app = AppScope.of(context);
  if (!await confirm(
    context,
    delete ? '永久删除设备历史？' : '停止设备同步？',
    delete ? '将删除该连接的样本、关联测量与目标，并重新计算统计，无法撤销。' : '保留原始历史记录，停止后续导入。',
  )) {
    return;
  }
  await app.device.write('health_auto_sync', null);
  if (device['provider'] == 'health_connect') await app.device.revokeHealth();
  await app.api.delete('/devices/${device['id']}?delete_history=$delete');
  app.refresh();
}

Future<void> privacySheet(BuildContext context) async {
  final app = AppScope.of(context);
  await editSheet(
    context,
    '个人数据与隐私',
    [
      const Field(
        'category',
        '数据类别',
        choices: {
          'all': '全部个人数据',
          'diet': '饮食记录',
          'fitness': '运动与设备',
          'agent': 'AI 对话与推荐',
          'profile': '身体档案',
        },
      ),
      const Field(
        'operation',
        '操作',
        choices: {
          'export': '导出 JSON',
          'diagnostics': '导出脱敏连接诊断',
          'delete': '预览并清空数据',
        },
      ),
    ],
    (body) async {
      final category = body['category'];
      if (body['operation'] == 'delete') {
        final preview = await app.api.get(
          '/privacy/delete-preview?category=$category',
        );
        if (!context.mounted) return;
        await editSheet(
          context,
          '确认永久清空',
          [
            Field(
              'phrase',
              '输入：${preview['confirmation_phrase']}',
              required: true,
            ),
          ],
          (typed) async {
            if (typed['phrase'] != preview['confirmation_phrase']) {
              throw ApiException('确认短语不匹配');
            }
            await app.deletePersonal(category, typed['phrase']);
          },
          introduction: note(
            '${preview['impact']}\n涉及约 ${preview['record_count']} 条记录，无法撤销。',
            color: P.red,
          ),
          button: '永久清空',
        );
      } else {
        if (!context.mounted ||
            !await confirm(context, '导出个人数据', '文件包含健康详情或使用记录，请保存到可信位置。')) {
          return;
        }
        final data = await app.api.get(
          body['operation'] == 'diagnostics'
              ? '/diagnostics/logs?limit=500'
              : '/privacy/export?category=$category',
        );
        await app.device.saveFile(
          'NutriPulse-$category-${today()}.json',
          Uint8List.fromList(
            utf8.encode(const JsonEncoder.withIndent('  ').convert(data)),
          ),
          'application/json',
        );
      }
    },
    button: '继续',
  );
}
