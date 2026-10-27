import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'core/api.dart';
import 'core/app_scope.dart';
import 'core/native_device.dart';
import 'features/diet/diet_page.dart';
import 'features/fitness/fitness_page.dart';
import 'features/eat/eat_page.dart';
import 'features/analytics/analytics_page.dart';
import 'features/profile/profile_page.dart';
import 'ui/design.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final device = NativeDevice();
  final settings = await device.settings();
  runApp(
    NutriPulse(
      controller: AppController(
        ApiClient(
          baseUrl: settings['url'] as String,
          token: settings['token'] as String,
        ),
        device,
      ),
    ),
  );
}

class NutriPulse extends StatelessWidget {
  final AppController controller;
  const NutriPulse({super.key, required this.controller});
  @override
  Widget build(BuildContext context) => AppScope(
    controller: controller,
    child: MaterialApp(
      title: 'NutriPulse',
      debugShowCheckedModeBanner: false,
      theme: appTheme(),
      locale: const Locale('zh', 'CN'),
      supportedLocales: const [Locale('zh', 'CN'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: const HomeShell(),
    ),
  );
}

class HomeShell extends StatelessWidget {
  const HomeShell({super.key});
  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    const labels = ['饮食', '健身', '吃什么', '数据', '我的'];
    const icons = [
      Icons.restaurant_rounded,
      Icons.fitness_center_rounded,
      Icons.auto_awesome,
      Icons.bar_chart_rounded,
      Icons.person_outline_rounded,
    ];
    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 54,
        titleSpacing: 20,
        title: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.favorite_rounded, color: P.green, size: 24),
            SizedBox(width: 7),
            Flexible(
              child: FittedBox(
                fit: BoxFit.scaleDown,
                child: Text(
                  'NutriPulse',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                ),
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: '电脑连接设置',
            onPressed: () => connectionSheet(context),
            icon: const Icon(Icons.wifi_rounded, color: P.muted),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: IndexedStack(
        index: app.tab,
        children: const [
          DietPage(),
          FitnessPage(),
          EatPage(),
          AnalyticsPage(),
          ProfilePage(),
        ],
      ),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          color: Colors.white,
          border: Border(top: BorderSide(color: P.line)),
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: 76,
            child: Row(
              children: List.generate(5, (i) {
                final selected = app.tab == i;
                return Expanded(
                  child: Semantics(
                    selected: selected,
                    button: true,
                    label: labels[i],
                    child: InkWell(
                      key: ValueKey('nav-$i'),
                      onTap: () => app.navigate(i),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Container(
                            width: i == 2 ? 42 : 38,
                            height: i == 2 ? 42 : 32,
                            decoration: BoxDecoration(
                              color: i == 2
                                  ? P.green
                                  : selected
                                  ? P.softGreen
                                  : Colors.transparent,
                              borderRadius: BorderRadius.circular(
                                i == 2 ? 15 : 11,
                              ),
                            ),
                            child: Icon(
                              icons[i],
                              size: i == 2 ? 24 : 23,
                              color: i == 2
                                  ? Colors.white
                                  : selected
                                  ? (i == 1 ? P.red : P.deepGreen)
                                  : P.muted,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            labels[i],
                            maxLines: 1,
                            style: TextStyle(
                              fontSize: 10,
                              color: selected ? P.deepGreen : P.muted,
                              fontWeight: selected
                                  ? FontWeight.w700
                                  : FontWeight.w400,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              }),
            ),
          ),
        ),
      ),
    );
  }
}
