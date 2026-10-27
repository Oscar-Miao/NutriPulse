import 'package:flutter/material.dart';
import '../../core/api.dart';
import '../../core/app_scope.dart';
import '../../core/data.dart';
import '../../ui/design.dart';
import '../../ui/forms.dart';

Future<void> mealSheet(
  BuildContext context,
  String date,
  String mealType, {
  Json? original,
  List<Json>? initialItems,
  String? scanId,
}) async {
  await showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (_) => MealEditor(
      date: date,
      mealType: mealType,
      original: original,
      initialItems: initialItems,
      scanId: scanId,
    ),
  );
}

class FoodFields {
  final Json original;
  final Map<String, TextEditingController> controls;
  String unit;
  final manuallyEditedNutrients = <String>{};
  FoodFields(Json item)
    : original = item,
      unit = item.s('unit').isEmpty ? 'g' : item.s('unit'),
      controls = {
        for (final key in [
          'display_name',
          'amount',
          'grams',
          'kcal',
          'carb_g',
          'protein_g',
          'fat_g',
          'fiber_g',
        ])
          key: TextEditingController(
            text:
                ['carb_g', 'protein_g', 'fat_g', 'fiber_g'].contains(key) &&
                    item.containsKey('nutrient_known_mask') &&
                    ((item['nutrient_known_mask'] as num).toInt() &
                            (1 <<
                                [
                                  'carb_g',
                                  'protein_g',
                                  'fat_g',
                                  'fiber_g',
                                ].indexOf(key))) ==
                        0
                ? ''
                : item[key]?.toString() ?? '',
          ),
      } {
    if (unit == 'g') controls['grams']!.text = controls['amount']!.text;
  }
  void changed(String key, String value) {
    const nutrients = ['kcal', 'carb_g', 'protein_g', 'fat_g', 'fiber_g'];
    if (nutrients.contains(key)) {
      manuallyEditedNutrients.add(key);
      return;
    }
    if (key != 'amount' && key != 'grams') return;
    final amount = double.tryParse(value);
    if (amount == null || !amount.isFinite || amount < 0) return;
    if (key == 'amount' && unit == 'g') controls['grams']!.text = value;
    final basis = key == 'grams' ? original.n('grams') : original.n('amount');
    if (basis <= 0 || (key == 'amount' && unit != original.s('unit'))) return;
    for (final nutrient in nutrients) {
      if (original[nutrient] != null &&
          !manuallyEditedNutrients.contains(nutrient) &&
          controls[nutrient]!.text.isNotEmpty) {
        controls[nutrient]!.text = (original.n(nutrient) * amount / basis)
            .toStringAsFixed(1);
      }
    }
    if (key == 'amount' && unit != 'g' && original['grams'] != null) {
      controls['grams']!.text = (original.n('grams') * amount / basis)
          .toStringAsFixed(1);
    }
  }

  Json payload() => {
    'display_name': controls['display_name']!.text.trim(),
    'amount': double.parse(controls['amount']!.text),
    'unit': unit,
    for (final key in [
      'grams',
      'kcal',
      'carb_g',
      'protein_g',
      'fat_g',
      'fiber_g',
    ])
      if (controls[key]!.text.trim().isNotEmpty)
        key: key == 'grams' && unit == 'g'
            ? double.parse(controls['amount']!.text)
            : double.parse(controls[key]!.text),
    if (unit == 'g') 'grams': double.parse(controls['amount']!.text),
    if (original['food_id'] != null &&
        controls['display_name']!.text.trim() == original.s('display_name'))
      'food_id': original['food_id'],
    if (original['confidence'] != null) 'confidence': original['confidence'],
    'user_edited': true,
  };
  void dispose() {
    for (final c in controls.values) {
      c.dispose();
    }
  }
}

class MealEditor extends StatefulWidget {
  final String date, mealType;
  final Json? original;
  final List<Json>? initialItems;
  final String? scanId;
  const MealEditor({
    super.key,
    required this.date,
    required this.mealType,
    this.original,
    this.initialItems,
    this.scanId,
  });
  @override
  State<MealEditor> createState() => _MealEditorState();
}

class _MealEditorState extends State<MealEditor> {
  final form = GlobalKey<FormState>();
  late final items =
      (widget.initialItems ??
              widget.original?.rows('items') ??
              [
                <String, dynamic>{'amount': 100, 'unit': 'g'},
              ])
          .map(FoodFields.new)
          .toList();
  late String meal = widget.mealType;
  late String status = widget.original?.s('status') ?? 'CONSUMED';
  bool busy = false, locked = false;
  String? error;
  PendingWrite? pending;
  @override
  void dispose() {
    for (final i in items) {
      i.dispose();
    }
    super.dispose();
  }

  Future<void> save() async {
    if (!form.currentState!.validate()) return;
    final app = AppScope.of(context);
    final body = {
      'local_date': widget.date,
      'meal_type': meal,
      'status': status,
      'items': items.map((i) => i.payload()).toList(),
    };
    setState(() {
      busy = true;
      error = null;
      locked = true;
    });
    try {
      if (widget.original != null) {
        await app.api.patch('/meals/${widget.original!['id']}', body);
        app.refresh();
      } else if (widget.scanId != null) {
        await app.api.post('/food-scans/${widget.scanId}/confirm', body);
        await app.device.clearPhotoDraft();
        app.refresh();
      } else {
        pending ??= PendingWrite('/meals', body);
        await persistAndSend(app, 'meal', pending!);
      }
      if (mounted) Navigator.pop(context);
    } on Exception catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> pickFood() async {
    final app = AppScope.of(context);
    final food = await showModalBottomSheet<Json>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => FoodSearch(app: app),
    );
    if (food == null || !mounted) return;
    setState(() {
      if (items.length == 1 &&
          items.first.controls['display_name']!.text.isEmpty) {
        items.removeAt(0).dispose();
      }
      items.add(FoodFields(food));
    });
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !busy,
    child: Padding(
      padding: EdgeInsets.fromLTRB(
        20,
        12,
        20,
        MediaQuery.viewInsetsOf(context).bottom + 20,
      ),
      child: Form(
        key: form,
        child: SizedBox(
          height: MediaQuery.sizeOf(context).height * .83,
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.scanId != null
                          ? '核对识餐明细'
                          : widget.original == null
                          ? '记录一餐'
                          : '编辑餐食',
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
              note('${widget.date} · 营养值填写当前份量的总量；未填写宏量保留为未知。'),
              Expanded(
                child: ListView(
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
                            onChanged: locked ? null : (v) => meal = v!,
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: DropdownButtonFormField<String>(
                            isExpanded: true,
                            initialValue: status,
                            decoration: const InputDecoration(
                              labelText: '记录状态',
                            ),
                            items: [
                              if (widget.scanId == null &&
                                  (widget.original == null ||
                                      status == 'PLANNED'))
                                const DropdownMenuItem(
                                  value: 'PLANNED',
                                  child: Text('计划吃'),
                                ),
                              const DropdownMenuItem(
                                value: 'CONSUMED',
                                child: Text('已吃过'),
                              ),
                            ],
                            onChanged: locked || widget.scanId != null
                                ? null
                                : (v) => status = v!,
                          ),
                        ),
                      ],
                    ),
                    for (var index = 0; index < items.length; index++)
                      Padding(
                        padding: const EdgeInsets.only(top: 14),
                        child: Panel(
                          color: P.background,
                          child: Column(
                            children: [
                              Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      '食物 ${index + 1}',
                                      style: const TextStyle(
                                        fontWeight: FontWeight.w700,
                                      ),
                                    ),
                                  ),
                                  if (items[index].original['confidence'] !=
                                      null)
                                    pill(
                                      '置信 ${display(items[index].original.n('confidence') * 100)}%',
                                    ),
                                  IconButton(
                                    onPressed: locked || items.length == 1
                                        ? null
                                        : () => setState(
                                            () =>
                                                items.removeAt(index).dispose(),
                                          ),
                                    icon: const Icon(
                                      Icons.remove_circle_outline,
                                      color: P.red,
                                    ),
                                  ),
                                ],
                              ),
                              foodInput(
                                items[index],
                                'display_name',
                                '食物名称',
                                required: true,
                              ),
                              Row(
                                children: [
                                  Expanded(
                                    child: foodInput(
                                      items[index],
                                      'amount',
                                      '份量数值',
                                      required: true,
                                      min: .01,
                                      max: 10000,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  SizedBox(
                                    width: 88,
                                    child: DropdownButtonFormField<String>(
                                      isExpanded: true,
                                      initialValue: items[index].unit,
                                      items: ['g', 'ml', '份', '个']
                                          .map(
                                            (u) => DropdownMenuItem(
                                              value: u,
                                              child: Text(u),
                                            ),
                                          )
                                          .toList(),
                                      onChanged: locked
                                          ? null
                                          : (v) => setState(() {
                                              items[index].unit = v!;
                                              items[index].changed(
                                                'amount',
                                                items[index]
                                                    .controls['amount']!
                                                    .text,
                                              );
                                            }),
                                    ),
                                  ),
                                ],
                              ),
                              Row(
                                children: [
                                  Expanded(
                                    child: foodInput(
                                      items[index],
                                      'grams',
                                      '对应克数（可空）',
                                      min: 0,
                                      max: 10000,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: foodInput(
                                      items[index],
                                      'kcal',
                                      '热量 kcal',
                                      required: true,
                                      min: 0,
                                      max: 20000,
                                    ),
                                  ),
                                ],
                              ),
                              Row(
                                children: [
                                  Expanded(
                                    child: foodInput(
                                      items[index],
                                      'carb_g',
                                      '碳水 g',
                                      min: 0,
                                      max: 2000,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: foodInput(
                                      items[index],
                                      'protein_g',
                                      '蛋白质 g',
                                      min: 0,
                                      max: 2000,
                                    ),
                                  ),
                                ],
                              ),
                              Row(
                                children: [
                                  Expanded(
                                    child: foodInput(
                                      items[index],
                                      'fat_g',
                                      '脂肪 g',
                                      min: 0,
                                      max: 2000,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: foodInput(
                                      items[index],
                                      'fiber_g',
                                      '纤维 g',
                                      min: 0,
                                      max: 2000,
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                    if (!locked && items.length < 30)
                      Wrap(
                        spacing: 8,
                        children: [
                          TextButton.icon(
                            onPressed: pickFood,
                            icon: const Icon(Icons.search),
                            label: const Text('食品库 / 常吃食物'),
                          ),
                          TextButton.icon(
                            onPressed: () => setState(
                              () => items.add(
                                FoodFields({'amount': 100, 'unit': 'g'}),
                              ),
                            ),
                            icon: const Icon(Icons.add),
                            label: const Text('添加食物'),
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
                    : error != null
                    ? '使用原内容重试'
                    : '确认并保存',
                busy ? null : save,
              ),
            ],
          ),
        ),
      ),
    ),
  );
  Widget foodInput(
    FoodFields item,
    String key,
    String label, {
    bool required = false,
    double? min,
    double? max,
  }) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: TextFormField(
      controller: item.controls[key],
      readOnly: locked || (key == 'grams' && item.unit == 'g'),
      onChanged: (value) => item.changed(key, value),
      decoration: InputDecoration(labelText: label),
      keyboardType: key == 'display_name'
          ? TextInputType.text
          : const TextInputType.numberWithOptions(decimal: true),
      validator: (raw) {
        final value = raw!.trim();
        if (value.isEmpty) return required ? '请填写' : null;
        if (key == 'display_name') return value.length > 100 ? '最多100字' : null;
        final n = double.tryParse(value);
        if (n == null ||
            !n.isFinite ||
            (min != null && n < min) ||
            (max != null && n > max)) {
          return '范围 $min–$max';
        }
        return null;
      },
    ),
  );
}

class FoodSearch extends StatefulWidget {
  final AppController app;
  const FoodSearch({super.key, required this.app});
  @override
  State<FoodSearch> createState() => _FoodSearchState();
}

class _FoodSearchState extends State<FoodSearch> {
  final search = TextEditingController();
  late Future<List<Json>> list = load('');
  Future<List<Json>> load(String q) async {
    final data = await widget.app.api.get(
      q.isEmpty ? '/foods/frequent' : '/foods?q=${Uri.encodeQueryComponent(q)}',
    );
    return data.rows('items');
  }

  @override
  void dispose() {
    search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.fromLTRB(
      20,
      20,
      20,
      MediaQuery.viewInsetsOf(context).bottom + 20,
    ),
    child: SizedBox(
      height: 420,
      child: Column(
        children: [
          TextField(
            controller: search,
            decoration: InputDecoration(
              labelText: '搜索食品库；空白时显示常吃食物',
              suffixIcon: IconButton(
                onPressed: () =>
                    setState(() => list = load(search.text.trim())),
                icon: const Icon(Icons.search),
              ),
            ),
            onSubmitted: (s) => setState(() => list = load(s)),
          ),
          Expanded(
            child: FutureBuilder<List<Json>>(
              future: list,
              builder: (context, state) {
                if (state.hasError) return Text(state.error.toString());
                if (!state.hasData) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (state.data!.isEmpty) {
                  return const Center(child: Text('暂无结果，可搜索或手工填写'));
                }
                return ListView(
                  children: state.data!
                      .map(
                        (food) => ListTile(
                          title: Text(food['name'] ?? food.s('display_name')),
                          subtitle: Text(
                            '${display(food['kcal'])} kcal · ${food['display_name'] == null ? '每100g' : '最近记录份量'}',
                          ),
                          onTap: () {
                            final frequent = food['display_name'] != null;
                            Navigator.pop(
                              context,
                              frequent
                                  ? food
                                  : {
                                      'food_id': food['id'],
                                      'display_name': food['name'],
                                      'amount': 100,
                                      'unit': 'g',
                                      'grams': 100,
                                      for (final key in [
                                        'kcal',
                                        'carb_g',
                                        'protein_g',
                                        'fat_g',
                                        'fiber_g',
                                      ])
                                        key: food[key],
                                    },
                            );
                          },
                        ),
                      )
                      .toList(),
                );
              },
            ),
          ),
        ],
      ),
    ),
  );
}
