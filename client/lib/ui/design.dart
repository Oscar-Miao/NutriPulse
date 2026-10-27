import 'package:flutter/material.dart';
import '../core/data.dart';

abstract final class P {
  static const green = Color(0xFF2ECC71),
      red = Color(0xFFFF5252),
      blue = Color(0xFF3498DB),
      yellow = Color(0xFFF1C40F),
      cyan = Color(0xFF00BEC5);
  static const background = Color(0xFFF8F9FA),
      ink = Color(0xFF20332B),
      muted = Color(0xFF7B8A83),
      deepGreen = Color(0xFF188B4E),
      softGreen = Color(0xFFEAF9F0),
      line = Color(0xFFEDF1EE);
}

ThemeData appTheme() => ThemeData(
  useMaterial3: true,
  scaffoldBackgroundColor: P.background,
  colorScheme: ColorScheme.fromSeed(
    seedColor: P.green,
    primary: P.deepGreen,
    surface: Colors.white,
  ),
  fontFamily: 'sans-serif',
  textTheme: const TextTheme(
    bodyMedium: TextStyle(color: P.ink, fontSize: 14, height: 1.5),
    titleLarge: TextStyle(
      color: P.ink,
      fontSize: 23,
      fontWeight: FontWeight.w800,
    ),
  ),
  inputDecorationTheme: InputDecorationTheme(
    filled: true,
    fillColor: P.background,
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(12),
      borderSide: const BorderSide(color: P.line),
    ),
    enabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(12),
      borderSide: const BorderSide(color: P.line),
    ),
    contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 13),
  ),
  filledButtonTheme: FilledButtonThemeData(
    style: FilledButton.styleFrom(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      minimumSize: const Size(0, 46),
    ),
  ),
  appBarTheme: const AppBarTheme(
    backgroundColor: P.background,
    surfaceTintColor: Colors.transparent,
    centerTitle: false,
  ),
);

class Panel extends StatelessWidget {
  final Widget child;
  final Color color;
  final EdgeInsets padding;
  const Panel({
    super.key,
    required this.child,
    this.color = Colors.white,
    this.padding = const EdgeInsets.all(18),
  });
  @override
  Widget build(BuildContext context) => Container(
    padding: padding,
    margin: const EdgeInsets.only(bottom: 14),
    decoration: BoxDecoration(
      color: color,
      borderRadius: BorderRadius.circular(16),
      boxShadow: const [
        BoxShadow(
          color: Color(0x0A000000),
          blurRadius: 22,
          offset: Offset(0, 5),
        ),
      ],
    ),
    child: Material(type: MaterialType.transparency, child: child),
  );
}

class PageBody extends StatelessWidget {
  final List<Widget> children;
  final Future<void> Function()? refresh;
  const PageBody({super.key, required this.children, this.refresh});
  @override
  Widget build(BuildContext context) {
    final body = ListView(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 96),
      physics: const AlwaysScrollableScrollPhysics(),
      children: children,
    );
    return refresh == null
        ? body
        : RefreshIndicator(onRefresh: refresh!, child: body);
  }
}

Widget title(String text, {String? subtitle, Widget? trailing}) => Padding(
  padding: const EdgeInsets.only(bottom: 18),
  child: Row(
    children: [
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              text,
              style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800),
            ),
            if (subtitle != null)
              Text(
                subtitle,
                style: const TextStyle(color: P.muted, fontSize: 12),
              ),
          ],
        ),
      ),
      ?trailing,
    ],
  ),
);
Widget section(String text, {Widget? trailing}) => Padding(
  padding: const EdgeInsets.only(top: 5, bottom: 12),
  child: Row(
    children: [
      Expanded(
        child: Text(
          text,
          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
        ),
      ),
      ?trailing,
    ],
  ),
);
Widget note(String text, {Color color = P.muted}) => Padding(
  padding: const EdgeInsets.symmetric(vertical: 5),
  child: Text(text, style: TextStyle(fontSize: 12, height: 1.5, color: color)),
);
Widget pill(
  String text, {
  Color color = P.deepGreen,
  Color background = P.softGreen,
  VoidCallback? onTap,
}) => Material(
  color: background,
  borderRadius: BorderRadius.circular(24),
  child: InkWell(
    onTap: onTap,
    borderRadius: BorderRadius.circular(24),
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      child: Text(
        text,
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    ),
  ),
);
Widget action(
  String text,
  VoidCallback? onTap, {
  Color color = P.deepGreen,
  IconData? icon,
}) => SizedBox(
  width: double.infinity,
  child: FilledButton.icon(
    style: FilledButton.styleFrom(backgroundColor: color),
    onPressed: onTap,
    icon: Icon(icon ?? Icons.arrow_forward_rounded, size: 18),
    label: Text(text),
  ),
);
Widget metric(
  String label,
  dynamic value, {
  String unit = '',
  Color color = P.ink,
  int digits = 0,
}) => Column(
  mainAxisSize: MainAxisSize.min,
  children: [
    FittedBox(
      fit: BoxFit.scaleDown,
      child: Text(
        '${display(value, digits)}${unit.isEmpty ? '' : ' $unit'}',
        style: TextStyle(
          color: color,
          fontSize: 20,
          fontWeight: FontWeight.w800,
        ),
      ),
    ),
    const SizedBox(height: 5),
    Text(label, style: const TextStyle(fontSize: 11, color: P.muted)),
  ],
);
Widget banner(
  String heading,
  String subtitle,
  IconData icon,
  VoidCallback onTap, {
  Color color = P.green,
}) => Padding(
  padding: const EdgeInsets.only(bottom: 14),
  child: Material(
    borderRadius: BorderRadius.circular(16),
    color: color,
    child: InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            Icon(icon, color: Colors.white, size: 31),
            const SizedBox(width: 13),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    heading,
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                      fontSize: 16,
                    ),
                  ),
                  Text(
                    subtitle,
                    style: const TextStyle(color: Colors.white, fontSize: 11),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right, color: Colors.white),
          ],
        ),
      ),
    ),
  ),
);
void message(BuildContext context, Object value) => ScaffoldMessenger.of(
  context,
).showSnackBar(SnackBar(content: Text(value.toString())));
Future<void> runTask(BuildContext context, Future<void> Function() task) async {
  try {
    await task();
  } on Exception catch (error) {
    if (context.mounted) message(context, error);
  }
}

Future<bool> confirm(
  BuildContext context,
  String heading,
  String content, {
  String label = '确认',
}) async =>
    await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(heading),
        content: SingleChildScrollView(child: Text(content)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(c, true),
            child: Text(label),
          ),
        ],
      ),
    ) ??
    false;

class RemoteData<T> extends StatefulWidget {
  final int revision;
  final Future<T> Function() load;
  final Widget Function(T) builder;
  final Widget Function(Object)? errorBuilder;
  const RemoteData({
    super.key,
    required this.revision,
    required this.load,
    required this.builder,
    this.errorBuilder,
  });
  @override
  State<RemoteData<T>> createState() => _RemoteDataState<T>();
}

class _RemoteDataState<T> extends State<RemoteData<T>> {
  late Future<T> future;
  @override
  void initState() {
    super.initState();
    future = widget.load();
  }

  @override
  void didUpdateWidget(covariant RemoteData<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.revision != widget.revision) future = widget.load();
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<T>(
    future: future,
    builder: (context, snapshot) {
      if (snapshot.hasError) {
        if (widget.errorBuilder != null) {
          return widget.errorBuilder!(snapshot.error!);
        }
        return Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Panel(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.cloud_off_rounded, size: 42, color: P.muted),
                  const SizedBox(height: 14),
                  Text(snapshot.error.toString()),
                  const SizedBox(height: 14),
                  action('重新连接', () => setState(() => future = widget.load())),
                ],
              ),
            ),
          ),
        );
      }
      if (!snapshot.hasData) {
        return const Center(child: CircularProgressIndicator(color: P.green));
      }
      return widget.builder(snapshot.data as T);
    },
  );
}
