import 'dart:async';
import 'package:flutter/material.dart';
import '../../core/api.dart';
import '../../core/app_scope.dart';
import '../../core/data.dart';
import '../../ui/design.dart';
import '../../ui/forms.dart';
import 'fitness_page.dart';
import 'prescription.dart';

Future<void> strengthSheet(BuildContext context, {Json? session}) async {
  final result = await showModalBottomSheet<Json>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (_) => StrengthEditor(session: session),
  );
  if (result != null && context.mounted) {
    await runTask(context, () => recoverySheet(context, result.s('id')));
  }
}

class SetFields {
  final bool timed;
  final int setNo;
  final TextEditingController name,
      amount,
      weight = TextEditingController(),
      rpe = TextEditingController(),
      rir = TextEditingController();
  bool completed = false;
  SetFields(String exercise, this.setNo, {this.timed = false, int target = 8})
    : name = TextEditingController(text: exercise),
      amount = TextEditingController(text: '$target');
  Json payload() => {
    'exercise_name': name.text.trim(),
    'set_no': setNo,
    'weight_kg': weight.text.isEmpty ? null : double.parse(weight.text),
    'reps': timed ? 0 : int.parse(amount.text),
    if (timed && int.parse(amount.text) > 0)
      'duration_sec': int.parse(amount.text),
    'completed': completed,
    if (rpe.text.isNotEmpty) 'rpe': double.parse(rpe.text),
    if (rir.text.isNotEmpty) 'rir': double.parse(rir.text),
  };
  void dispose() {
    for (final c in [name, amount, weight, rpe, rir]) {
      c.dispose();
    }
  }
}

class StrengthEditor extends StatefulWidget {
  final Json? session;
  const StrengthEditor({super.key, this.session});
  @override
  State<StrengthEditor> createState() => _StrengthEditorState();
}

class _StrengthEditorState extends State<StrengthEditor> {
  final form = GlobalKey<FormState>();
  final minutes = TextEditingController(text: '45');
  late final List<SetFields> sets = widget.session == null
      ? [SetFields('', 1)]
      : [
          for (final text in widget.session!['exercises'] as List)
            ...fromPrescription(text.toString()),
        ];
  Timer? timer;
  DateTime? restEnd;
  int remaining = 0;
  bool busy = false, locked = false;
  String? error;
  PendingWrite? pending;
  List<SetFields> fromPrescription(String value) {
    final p = Prescription.parse(value);
    return List.generate(
      p.sets,
      (i) => SetFields(p.name, i + 1, timed: p.timed, target: p.amount),
    );
  }

  void rest([int seconds = 90]) {
    timer?.cancel();
    restEnd = DateTime.now().add(Duration(seconds: seconds));
    setState(() => remaining = seconds);
    timer = Timer.periodic(const Duration(seconds: 1), (t) {
      final count = restEnd!.difference(DateTime.now()).inSeconds;
      setState(() => remaining = count.clamp(0, seconds));
      if (count <= 0) {
        t.cancel();
        if (mounted) message(context, '休息结束，可以开始下一组');
      }
    });
  }

  @override
  void dispose() {
    timer?.cancel();
    minutes.dispose();
    for (final s in sets) {
      s.dispose();
    }
    super.dispose();
  }

  Future<void> save() async {
    if (!form.currentState!.validate()) return;
    if (!sets.any((s) => s.completed)) {
      message(context, '请至少完成一组');
      return;
    }
    final app = AppScope.of(context);
    if (widget.session != null &&
        sets.any((s) => !s.completed) &&
        !locked &&
        !await confirm(context, '保存部分完成的训练？', '将按实际组数保存，服务端依照计划标准判定完成状态。')) {
      return;
    }
    pending ??= PendingWrite('/workouts', {
      'workout_type': 'strength',
      'minutes': double.parse(minutes.text),
      'local_date': widget.session?['scheduled_date'] ?? today(),
      'sets': sets.map((s) => s.payload()).toList(),
      if (widget.session != null) 'plan_session_id': widget.session!['id'],
    });
    setState(() {
      busy = true;
      locked = true;
      error = null;
    });
    try {
      final result = await persistAndSend(app, 'workout', pending!);
      if (!mounted) return;
      Navigator.pop(context, result);
    } on Exception catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !busy,
    child: Padding(
      padding: EdgeInsets.fromLTRB(
        18,
        12,
        18,
        MediaQuery.viewInsetsOf(context).bottom + 18,
      ),
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * .85,
        child: Form(
          key: form,
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.session?.s('title') ?? '力量训练记录',
                      style: const TextStyle(
                        fontSize: 21,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                  IconButton(
                    onPressed: busy ? null : () => Navigator.pop(context),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
              Row(
                children: [
                  Expanded(child: input(minutes, '实际训练分钟', 1, 1440)),
                  const SizedBox(width: 10),
                  pill(
                    remaining > 0 ? '休息 ${remaining}s · 重置' : '组间休息 90s',
                    color: P.red,
                    background: const Color(0xFFFFEEEE),
                    onTap: () => rest(),
                  ),
                ],
              ),
              note('重量留空表示自重；计时组填写秒数，不计入重量×次数容量。'),
              Expanded(
                child: ListView(
                  children: [
                    for (var i = 0; i < sets.length; i++)
                      Panel(
                        color: P.background,
                        child: Column(
                          children: [
                            Row(
                              children: [
                                Text(
                                  '第 ${sets[i].setNo} 组${sets[i].timed ? ' · 计时' : ''}',
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                const Spacer(),
                                if (widget.session == null)
                                  IconButton(
                                    onPressed: locked || sets.length <= 1
                                        ? null
                                        : () => setState(
                                            () => sets.removeAt(i).dispose(),
                                          ),
                                    icon: const Icon(
                                      Icons.remove_circle_outline,
                                      color: P.red,
                                    ),
                                  ),
                              ],
                            ),
                            TextFormField(
                              controller: sets[i].name,
                              readOnly: locked || widget.session != null,
                              decoration: const InputDecoration(
                                labelText: '动作名称',
                              ),
                              validator: (v) =>
                                  v!.trim().isEmpty || v.trim().length > 100
                                  ? '动作名称需为1–100字'
                                  : null,
                            ),
                            Row(
                              children: [
                                Expanded(
                                  child: input(
                                    sets[i].weight,
                                    '重量 kg（自重留空）',
                                    0,
                                    1000,
                                    optional: true,
                                  ),
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: input(
                                    sets[i].amount,
                                    sets[i].timed ? '持续秒数' : '次数',
                                    0,
                                    sets[i].timed ? 3600 : 1000,
                                    integer: true,
                                  ),
                                ),
                              ],
                            ),
                            ExpansionTile(
                              tilePadding: EdgeInsets.zero,
                              title: const Text(
                                '主观强度（可选）',
                                style: TextStyle(fontSize: 12),
                              ),
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: input(
                                        sets[i].rpe,
                                        'RPE 0–10',
                                        0,
                                        10,
                                        optional: true,
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: input(
                                        sets[i].rir,
                                        'RIR 0–10',
                                        0,
                                        10,
                                        optional: true,
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                            CheckboxListTile(
                              contentPadding: EdgeInsets.zero,
                              title: const Text(
                                '本组已完成',
                                style: TextStyle(fontSize: 13),
                              ),
                              value: sets[i].completed,
                              onChanged: locked
                                  ? null
                                  : (v) {
                                      setState(() => sets[i].completed = v!);
                                      if (v == true) rest();
                                    },
                            ),
                          ],
                        ),
                      ),
                    if (widget.session == null && sets.length < 100)
                      Wrap(
                        children: [
                          TextButton.icon(
                            onPressed: locked
                                ? null
                                : () => setState(
                                    () => sets.add(
                                      SetFields(
                                        sets.last.name.text,
                                        sets.length + 1,
                                      ),
                                    ),
                                  ),
                            icon: const Icon(Icons.add),
                            label: const Text('添加次数组'),
                          ),
                          TextButton.icon(
                            onPressed: locked
                                ? null
                                : () => setState(
                                    () => sets.add(
                                      SetFields(
                                        '',
                                        sets.length + 1,
                                        timed: true,
                                        target: 20,
                                      ),
                                    ),
                                  ),
                            icon: const Icon(Icons.timer_outlined),
                            label: const Text('添加计时组'),
                          ),
                        ],
                      ),
                  ],
                ),
              ),
              if (error != null) note(error!, color: P.red),
              action(
                busy
                    ? '正在保存…'
                    : error == null
                    ? '保存训练记录'
                    : '使用原内容重试',
                busy ? null : save,
                color: P.red,
              ),
            ],
          ),
        ),
      ),
    ),
  );
  Widget input(
    TextEditingController c,
    String label,
    double min,
    double max, {
    bool optional = false,
    bool integer = false,
  }) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 7),
    child: TextFormField(
      controller: c,
      readOnly: locked,
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      decoration: InputDecoration(labelText: label),
      validator: (raw) {
        final s = raw!.trim();
        if (s.isEmpty) return optional ? null : '请填写';
        final n = num.tryParse(s);
        if (n == null ||
            !n.isFinite ||
            n < min ||
            n > max ||
            (integer && n != n.roundToDouble())) {
          return '范围 $min–$max${integer ? '，需整数' : ''}';
        }
        if (c != minutes &&
            sets.any((set) => set.amount == c && set.completed) &&
            n == 0) {
          return '完成组需大于0';
        }
        return null;
      },
    ),
  );
}
