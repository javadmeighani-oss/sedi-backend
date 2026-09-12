import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/locale/sedi_locale_controller.dart';
import 'package:sedi_app/features/devices/presentation/pages/devices_page.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/pages/gate3_interactive_page.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/pages/gate3_profile_page.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/a3_page_app_bar.dart';
import 'package:sedi_app/features/lifestyle/presentation/pages/lifestyle_exercise_page.dart';
import 'package:sedi_app/features/lifestyle/presentation/pages/lifestyle_health_page.dart';
import 'package:sedi_app/features/lifestyle/presentation/pages/lifestyle_history_page.dart';
import 'package:sedi_app/features/lifestyle/presentation/pages/lifestyle_nutrition_page.dart';
import 'package:sedi_app/features/lifestyle/presentation/pages/lifestyle_page.dart';
import 'package:sedi_app/features/lifestyle/presentation/pages/lifestyle_schedule_page.dart';
import 'package:sedi_app/features/notifications/presentation/pages/notification_inbox_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

String _read(String relativePath) => File(relativePath).readAsStringSync();

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    SediLocaleController.instance.debugResetForTest();
  });

  test('1 shared A3 Back primitive is the single destination contract', () {
    final shared = _read(
      'lib/features/gate3_interactive/presentation/widgets/a3_page_app_bar.dart',
    );
    expect(shared.contains('class A3BackButton'), isTrue);
    expect(shared.contains('class A3PageAppBar'), isTrue);
    expect(shared.contains('BackButton'), isTrue);
    expect(shared.contains('AppTheme.textPrimary'), isTrue);
    expect(shared.contains('leading: const A3BackButton()'), isTrue);
    expect(shared.contains('SediLocaleController'), isFalse);
    expect(shared.contains('ApiClient'), isFalse);
    expect(shared.contains('Navigator.push'), isFalse);

    final pages = <String, String>{
      'profile':
          'lib/features/gate3_interactive/presentation/pages/gate3_profile_page.dart',
      'lifestyle':
          'lib/features/lifestyle/presentation/pages/lifestyle_page.dart',
      'health':
          'lib/features/lifestyle/presentation/pages/lifestyle_health_page.dart',
      'history':
          'lib/features/lifestyle/presentation/pages/lifestyle_history_page.dart',
      'schedule':
          'lib/features/lifestyle/presentation/pages/lifestyle_schedule_page.dart',
      'weekly':
          'lib/features/lifestyle/presentation/widgets/lifestyle_weekly_plan_view.dart',
      'devices': 'lib/features/devices/presentation/pages/devices_page.dart',
      'notifications':
          'lib/features/notifications/presentation/pages/notification_inbox_page.dart',
    };
    for (final e in pages.entries) {
      final src = _read(e.value);
      expect(src.contains('A3PageAppBar'), isTrue, reason: e.key);
      expect(src.contains('a3_page_app_bar.dart'), isTrue, reason: e.key);
    }

    final root = _read(
      'lib/features/gate3_interactive/presentation/pages/gate3_interactive_page.dart',
    );
    expect(root.contains('A3PageAppBar'), isFalse);
    expect(root.contains('A3BackButton'), isFalse);
  });

  test('10 interaction/theme tokens preserved on shared Back', () {
    final shared = _read(
      'lib/features/gate3_interactive/presentation/widgets/a3_page_app_bar.dart',
    );
    expect(shared.contains('AppTheme.textPrimary'), isTrue);
    expect(shared.contains('Color(0x'), isFalse);
    expect(shared.contains('Duration('), isFalse);
    expect(shared.contains('Future.delayed'), isFalse);
  });

  test('12/13 root exit + initialDraft composer-only preserved', () {
    final page = _read(
      'lib/features/gate3_interactive/presentation/pages/gate3_interactive_page.dart',
    );
    expect(page.contains('routeCanPop'), isTrue);
    expect(page.contains('ModalRoute.of(context)?.canPop'), isTrue);
    expect(page.contains('canPop: routeCanPop'), isTrue);
    expect(page.contains('_handleBackPress'), isTrue);
    expect(page.contains('SystemNavigator.pop'), isTrue);
    expect(page.contains('initialDraft'), isTrue);
    expect(page.contains('initialText: widget.initialDraft'), isTrue);
    expect(page.contains('sendUserMessage(widget.initialDraft'), isFalse);

    final lifestyle = _read(
      'lib/features/lifestyle/presentation/pages/lifestyle_page.dart',
    );
    expect(lifestyle.contains('openLifestyleChat'), isTrue);
    expect(lifestyle.contains('Gate3InteractivePage(initialDraft:'), isTrue);
  });

  Future<void> pushDestination(
    WidgetTester tester, {
    required Widget page,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            return Scaffold(
              body: Center(
                child: ElevatedButton(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute<void>(builder: (_) => page),
                    );
                  },
                  child: const Text('go'),
                ),
              ),
            );
          },
        ),
      ),
    );
    await tester.tap(find.text('go'));
    await tester.pump(); // first destination frame (before async redirects)
  }

  testWidgets('2 Profile Back pops one route to prior (A3)', (tester) async {
    await pushDestination(tester, page: const Gate3ProfilePage());
    expect(find.byType(A3BackButton), findsOneWidget);
    expect(find.byType(Gate3ProfilePage), findsOneWidget);
    await tester.tap(find.byType(A3BackButton));
    await tester.pumpAndSettle();
    expect(find.byType(Gate3ProfilePage), findsNothing);
    expect(find.text('go'), findsOneWidget);
  });

  testWidgets('3 Lifestyle hub Back pops one route', (tester) async {
    await pushDestination(tester, page: const LifestylePage());
    expect(find.byType(LifestylePage), findsOneWidget);
    await tester.tap(find.byType(A3BackButton));
    await tester.pumpAndSettle();
    expect(find.byType(LifestylePage), findsNothing);
  });

  testWidgets('4 all five Lifestyle sections Back to prior route',
      (tester) async {
    final sections = <Widget>[
      const LifestyleHealthPage(),
      const LifestyleHistoryPage(),
      const LifestyleSchedulePage(),
      const LifestyleNutritionPage(),
      const LifestyleExercisePage(),
    ];
    for (final page in sections) {
      await pushDestination(tester, page: page);
      expect(find.byType(A3BackButton), findsOneWidget);
      await tester.tap(find.byType(A3BackButton));
      await tester.pumpAndSettle();
      expect(find.byType(A3BackButton), findsNothing);
    }
  });

  testWidgets('5 Devices Back pops one route', (tester) async {
    await pushDestination(tester, page: const DevicesPage());
    expect(find.byType(DevicesPage), findsOneWidget);
    await tester.tap(find.byType(A3BackButton));
    await tester.pumpAndSettle();
    expect(find.byType(DevicesPage), findsNothing);
  });

  testWidgets('6 Notifications Back pops one route', (tester) async {
    await pushDestination(tester, page: const NotificationInboxPage());
    expect(find.byType(A3BackButton), findsOneWidget);
    await tester.tap(find.byType(A3BackButton));
    await tester.pumpAndSettle();
    expect(find.byType(NotificationInboxPage), findsNothing);
  });

  testWidgets('7 LTR leading semantics — Back on start/leading side',
      (tester) async {
    await SediLocaleController.instance
        .setRuntimeLocale('en', persistBootstrapCache: false);
    await pushDestination(tester, page: const LifestylePage());
    await tester.pumpAndSettle();
    final back = tester.getCenter(find.byType(A3BackButton));
    final title = tester.getCenter(find.text('Lifestyle'));
    expect(back.dx, lessThan(title.dx));
  });

  testWidgets('8 RTL leading semantics — Back on start/leading side',
      (tester) async {
    await SediLocaleController.instance
        .setRuntimeLocale('fa', persistBootstrapCache: false);
    await pushDestination(tester, page: const LifestylePage());
    await tester.pumpAndSettle();
    final back = tester.getCenter(find.byType(A3BackButton));
    final title = tester.getCenter(find.text('سبک زندگی'));
    expect(back.dx, greaterThan(title.dx));
  });

  testWidgets('9 Back pops exactly one route (hub under section)',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            return Scaffold(
              body: Center(
                child: ElevatedButton(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => const LifestylePage(),
                      ),
                    );
                  },
                  child: const Text('root'),
                ),
              ),
            );
          },
        ),
      ),
    );
    await tester.tap(find.text('root'));
    await tester.pumpAndSettle();
    expect(find.byType(LifestylePage), findsOneWidget);

    await tester.tap(find.text('Health'));
    await tester.pumpAndSettle();
    expect(find.byType(LifestyleHealthPage), findsOneWidget);
    expect(find.byType(LifestylePage), findsNothing);

    await tester.tap(find.byType(A3BackButton));
    await tester.pumpAndSettle();
    expect(find.byType(LifestyleHealthPage), findsNothing);
    expect(find.byType(LifestylePage), findsOneWidget);
    expect(find.text('root'), findsNothing);
  });

  testWidgets('11 Lifestyle → Chat Back returns to Lifestyle route',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: LifestylePage()),
    );
    await tester.pumpAndSettle();

    openLifestyleChat(
      tester.element(find.byType(LifestylePage)),
      initialDraft: 'draft-only',
    );
    await tester.pumpAndSettle();

    expect(find.byType(Gate3InteractivePage), findsOneWidget);
    expect(find.byType(LifestylePage), findsNothing);

    final navigator = tester.state<NavigatorState>(find.byType(Navigator));
    expect(navigator.canPop(), isTrue);
    navigator.pop();
    await tester.pumpAndSettle();

    expect(find.byType(Gate3InteractivePage), findsNothing);
    expect(find.byType(LifestylePage), findsOneWidget);
  });

  testWidgets('12 root Gate3InteractivePage exit policy still blocks first pop',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: Gate3InteractivePage()),
    );
    await tester.pump();

    final navigator = tester.state<NavigatorState>(find.byType(Navigator));
    expect(navigator.canPop(), isFalse);

    await tester.binding.handlePopRoute();
    await tester.pump();
    expect(find.byType(Gate3InteractivePage), findsOneWidget);
    expect(find.text('Press back again to exit'), findsOneWidget);
  });

  testWidgets('13 initialDraft seeds composer only (no auto-send)',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Gate3InteractivePage(initialDraft: 'compose me'),
      ),
    );
    await tester.pump();

    expect(find.text('compose me'), findsOneWidget);
    final pageSrc = _read(
      'lib/features/gate3_interactive/presentation/pages/gate3_interactive_page.dart',
    );
    expect(pageSrc.contains('initialText: widget.initialDraft'), isTrue);
    expect(pageSrc.contains('sendUserMessage(widget.initialDraft'), isFalse);
  });

  test('A3BackButton uses Material semantics / tooltip contract', () {
    final shared = _read(
      'lib/features/gate3_interactive/presentation/widgets/a3_page_app_bar.dart',
    );
    expect(shared.contains('BackButton'), isTrue);
    expect(shared.contains('IconButton('), isFalse);
  });
}
