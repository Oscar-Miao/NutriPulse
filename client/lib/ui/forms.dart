import 'dart:convert';
import 'package:flutter/material.dart';
import '../core/api.dart';
import '../core/data.dart';
import '../core/app_scope.dart';
import 'design.dart';

class Field {
  final String key, label;
  final dynamic value;
  final Map<String, String>? choices;
  final bool numeric, integer, required, multiline, obscure;
  final double? min, max;
  const Field(
    this.key,
    this.label, {
    this.value,
    this.choices,
    this.numeric = false,
    this.integer = false,
    this.required = false,
    this.multiline = false,
    this.obscure = false,
    this.min,
    this.max,
  });
}

Future<bool> editSheet(
  BuildContext context,
  String title,
  List<Field> fields,
  Future<void> Function(Json) save, {
  Widget? introduction,
  String button = '保存',
  bool freeze = false,
}) async =>
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.white,
      builder: (_) => EditorSheet(
        title: title,
        fields: fields,
        save: save,
        introduction: introduction,
        button: button,
        freeze: freeze,
      ),
    ) ??
    false;

class EditorSheet extends StatefulWidget {
  final String title, button;
  final List<Field> fields;
  final Future<void> Function(Json) save;
  final Widget? introduction;
  final bool freeze;
  const EditorSheet({
    super.key,
    required this.title,
    required this.fields,
    required this.save,
    required this.button,
    this.introduction,
    this.freeze = false,
  });
  @override
  State<EditorSheet> createState() => _EditorSheetState();
}

class _EditorSheetState extends State<EditorSheet> {
  final form = GlobalKey<FormState>();
  late final controls = {
    for (final f in widget.fields)
      f.key: TextEditingController(text: f.value?.toString() ?? ''),
  };
  late final choices = {
    for (final f in widget.fields.where((f) => f.choices != null))
      f.key: f.value?.toString() ?? f.choices!.keys.first,
  };
  bool busy = false, locked = false;
  String? error;
  Json? frozen;
  @override
  void dispose() {
    for (final c in controls.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> submit() async {
    if (!form.currentState!.validate()) return;
    final body =
        frozen ??
        <String, dynamic>{
          for (final f in widget.fields)
            f.key: f.choices != null
                ? choices[f.key]
                : controls[f.key]!.text.trim().isEmpty
                ? null
                : f.numeric
                ? (f.integer
                      ? int.parse(controls[f.key]!.text.trim())
                      : double.parse(controls[f.key]!.text.trim()))
                : controls[f.key]!.text.trim(),
        };
    if (widget.freeze) frozen = body;
    setState(() {
      busy = true;
      locked = widget.freeze;
      error = null;
    });
    try {
      await widget.save(body);
      if (mounted) Navigator.pop(context, true);
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
        22,
        18,
        22,
        MediaQuery.viewInsetsOf(context).bottom + 22,
      ),
      child: SingleChildScrollView(
        child: Form(
          key: form,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.title,
                      style: const TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                  IconButton(
                    onPressed: busy
                        ? null
                        : () => Navigator.pop(context, false),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
              ?widget.introduction,
              for (final f in widget.fields)
                Padding(
                  padding: const EdgeInsets.only(top: 13),
                  child: f.choices != null
                      ? DropdownButtonFormField<String>(
                          initialValue: choices[f.key],
                          isExpanded: true,
                          decoration: InputDecoration(labelText: f.label),
                          items: f.choices!.entries
                              .map(
                                (e) => DropdownMenuItem(
                                  value: e.key,
                                  child: Text(e.value),
                                ),
                              )
                              .toList(),
                          onChanged: locked || busy
                              ? null
                              : (v) => choices[f.key] = v!,
                        )
                      : TextFormField(
                          controller: controls[f.key],
                          obscureText: f.obscure,
                          readOnly: locked || busy,
                          minLines: f.multiline ? 2 : 1,
                          maxLines: f.multiline ? 4 : 1,
                          decoration: InputDecoration(labelText: f.label),
                          keyboardType: f.numeric
                              ? const TextInputType.numberWithOptions(
                                  decimal: true,
                                )
                              : TextInputType.text,
                          validator: (raw) {
                            final value = raw!.trim();
                            if (value.isEmpty) {
                              return f.required ? '请填写${f.label}' : null;
                            }
                            if (f.numeric) {
                              final n = num.tryParse(value);
                              if (n == null ||
                                  !n.isFinite ||
                                  (f.integer && n != n.roundToDouble())) {
                                return f.integer ? '请输入整数' : '请输入有效数字';
                              }
                              if ((f.min != null && n < f.min!) ||
                                  (f.max != null && n > f.max!)) {
                                return '范围：${f.min ?? '不限'}–${f.max ?? '不限'}';
                              }
                            }
                            return null;
                          },
                        ),
                ),
              if (error != null) note(error!, color: P.red),
              if (locked && error != null) note('请求内容已锁定。重试使用相同内容，避免重复记账。'),
              const SizedBox(height: 18),
              action(
                busy
                    ? '正在保存…'
                    : error != null && locked
                    ? '使用原内容重试'
                    : widget.button,
                busy ? null : submit,
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

Future<Json> persistAndSend(
  AppController app,
  String kind,
  PendingWrite write,
) async {
  // Implemented with the same operation key across process restarts.
  final existing = await app.device.read('pending_$kind');
  if (existing != null && object(jsonDecode(existing))['key'] != write.key) {
    throw ApiException('有一条结果未确认的请求，请先在页面中重试或处理它');
  }
  write.serverUrl ??= app.api.baseUrl;
  await app.device.write('pending_$kind', jsonEncode(write.toJson()));
  final result = await write.send(app.api);
  await app.device.write('pending_$kind', null);
  app.refresh();
  return result;
}

class PendingBanner extends StatelessWidget {
  final String kind;
  const PendingBanner(this.kind, {super.key});
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    return FutureBuilder<String?>(
      future: app.device.read('pending_$kind'),
      builder: (context, state) {
        if (!state.hasData) return const SizedBox.shrink();
        final write = PendingWrite.fromJson(object(jsonDecode(state.data!)));
        return Panel(
          color: const Color(0xFFFFF6E3),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '有一条保存请求的结果尚未确认',
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
              note(
                '日期 ${write.payload['local_date'] ?? ''} · ${write.serverUrl ?? app.api.baseUrl}',
              ),
              Wrap(
                spacing: 8,
                children: [
                  pill(
                    '使用原内容重试',
                    onTap: () => runTask(context, () async {
                      await persistAndSend(app, kind, write);
                    }),
                  ),
                  pill(
                    '查看内容 / 放弃重试',
                    onTap: () => runTask(context, () async {
                      if (await confirm(
                        context,
                        '放弃本机待处理请求？',
                        '${const JsonEncoder.withIndent('  ').convert(write.payload)}\n\n请求可能已在电脑服务保存。放弃只删除本机待重试内容，先检查账本再新建记录。',
                        label: '放弃重试',
                      )) {
                        await app.device.write('pending_$kind', null);
                        app.refresh();
                      }
                    }),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}
