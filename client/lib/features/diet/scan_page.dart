import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import '../../core/app_scope.dart';
import '../../core/data.dart';
import '../../ui/design.dart';
import 'meal_editor.dart';

Future<void> chooseScan(BuildContext context, String date) async {
  final app = AppScope.of(context);
  final camera = await showModalBottomSheet<bool>(
    context: context,
    builder: (c) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            leading: const Icon(Icons.camera_alt_outlined),
            title: const Text('拍一张照片'),
            onTap: () => Navigator.pop(c, true),
          ),
          ListTile(
            leading: const Icon(Icons.photo_library_outlined),
            title: const Text('从相册选择'),
            onTap: () => Navigator.pop(c, false),
          ),
        ],
      ),
    ),
  );
  if (camera == null || !context.mounted) return;
  await runTask(context, () async {
    final bytes = await app.device.photo(camera);
    if (bytes != null && context.mounted) {
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) =>
              ScanPage(bytes: bytes, operation: operationKey(), date: date),
        ),
      );
    }
  });
}

class ScanPage extends StatefulWidget {
  final Uint8List bytes;
  final String operation, date;
  const ScanPage({
    super.key,
    required this.bytes,
    required this.operation,
    required this.date,
  });
  @override
  State<ScanPage> createState() => _ScanPageState();
}

class _ScanPageState extends State<ScanPage> {
  Json? scan;
  bool busy = false, started = false;
  String? error;
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!started) {
      started = true;
      identify();
    }
  }

  Future<void> identify() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final result = await AppScope.of(context).api.post('/food-scans', {
        'image_base64': base64Encode(widget.bytes),
        'mime_type': 'image/jpeg',
      }, widget.operation);
      if (mounted) setState(() => scan = result);
    } on Exception catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context),
        result = scan?.obj('result') ?? <String, dynamic>{};
    return Scaffold(
      appBar: AppBar(title: const Text('AI Food Scanner')),
      body: PageBody(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: Image.memory(
              widget.bytes,
              height: 210,
              width: double.infinity,
              fit: BoxFit.cover,
            ),
          ),
          const SizedBox(height: 18),
          if (busy) const LinearProgressIndicator(color: P.green),
          if (busy) note('本地电脑正在调用联网多模态 Agent，结果返回后请人工核对。'),
          if (error != null)
            Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(error!, style: const TextStyle(color: P.red)),
                  const SizedBox(height: 12),
                  action('重试识别', identify),
                  TextButton(
                    onPressed: () => runTask(context, () async {
                      if (await confirm(
                        context,
                        '加密暂存到本机？',
                        '照片将加密保存在当前设备，之后可在饮食页重试或删除。',
                      )) {
                        await app.device.savePhotoDraft(
                          widget.bytes,
                          widget.operation,
                        );
                        if (context.mounted) message(context, '已加密保存在本机');
                      }
                    }),
                    child: const Text('加密保存草稿，稍后重试'),
                  ),
                ],
              ),
            ),
          if (scan != null) ...[
            section('识别结果', trailing: pill('AI 估算 · 待核对', color: P.blue)),
            if (scan!['status'] == 'PROCESSING')
              action(
                '任务仍在处理中，点击查询',
                () => runTask(context, () async {
                  final value = await app.api.get('/food-scans/${scan!['id']}');
                  if (mounted) setState(() => scan = value);
                }),
              ),
            for (final item in result.rows('items'))
              Panel(
                color: const Color(0xFFF0F8FD),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    section(
                      item.s('name'),
                      trailing: pill(
                        '${display(item.n('confidence') * 100)}% 置信',
                        color: P.blue,
                      ),
                    ),
                    Text(
                      '${display(item['estimated_grams'])} g · ${display(item['kcal'])} kcal',
                      style: const TextStyle(
                        fontSize: 21,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    note(
                      '碳水 ${display(item['carb_g'], 1)}g · 蛋白 ${display(item['protein_g'], 1)}g · 脂肪 ${display(item['fat_g'], 1)}g',
                    ),
                    for (final text in (item['assumptions'] as List?) ?? [])
                      note(text.toString()),
                  ],
                ),
              ),
            for (final text in (result['uncertainties'] as List?) ?? [])
              note(text.toString(), color: P.red),
            if (scan!['status'] == 'REVIEW_REQUIRED')
              action('核对克数与热量后记入', () async {
                await mealSheet(
                  context,
                  widget.date,
                  'lunch',
                  scanId: scan!.s('id'),
                  initialItems: result
                      .rows('items')
                      .map(
                        (i) => {
                          'display_name': i['name'],
                          'amount': i['estimated_grams'],
                          'unit': 'g',
                          'grams': i['estimated_grams'],
                          for (final key in [
                            'kcal',
                            'carb_g',
                            'protein_g',
                            'fat_g',
                            'confidence',
                          ])
                            key: i[key],
                        },
                      )
                      .toList(),
                );
                if (!mounted) return;
                final latest = await app.api.get('/food-scans/${scan!['id']}');
                if (latest['status'] == 'CONFIRMED' && context.mounted) {
                  Navigator.pop(context);
                }
              }),
            if (scan!['status'] == 'CONFIRMED') note('该识餐已入账，可到饮食页编辑。'),
          ],
        ],
      ),
    );
  }
}
