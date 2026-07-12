import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/gate3_interactive/models/gate3_interaction_state.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_brain_orb.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_brand_lockup.dart';

void main() {
  test('SediBrainOrb brand label is fixed Latin', () {
    expect(SediBrainOrb.brandLabel, 'Sedi.');
    expect(SediBrandLockup.label, 'Sedi.');
  });

  testWidgets('Sedi brand lockup stays Sedi. under RTL and LTR', (tester) async {
    for (final direction in [TextDirection.rtl, TextDirection.ltr]) {
      await tester.pumpWidget(
        MaterialApp(
          home: Directionality(
            textDirection: direction,
            child: const Scaffold(
              body: Center(
                child: SediBrandLockup(fontSize: 24),
              ),
            ),
          ),
        ),
      );

      expect(find.byType(Directionality), findsWidgets);
      final lockupDirectionality = tester.widget<Directionality>(
        find
            .ancestor(
              of: find.text('Sedi.'),
              matching: find.byWidgetPredicate(
                (widget) =>
                    widget is Directionality &&
                    widget.textDirection == TextDirection.ltr,
              ),
            )
            .first,
      );
      expect(lockupDirectionality.textDirection, TextDirection.ltr);

      final textWidget = tester.widget<Text>(find.text('Sedi.'));
      expect(textWidget.data, 'Sedi.');
      expect(textWidget.textDirection, TextDirection.ltr);
      expect(textWidget.data!.indexOf('.'), textWidget.data!.length - 1);
    }
  });

  testWidgets('Sedi brand lockup stays Sedi. inside Persian page direction',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        locale: Locale('fa'),
        home: Directionality(
          textDirection: TextDirection.rtl,
          child: Scaffold(
            body: Center(
              child: SediBrandLockup(fontSize: 24),
            ),
          ),
        ),
      ),
    );

    final textWidget = tester.widget<Text>(find.text('Sedi.'));
    expect(textWidget.data, 'Sedi.');
    expect(textWidget.textDirection, TextDirection.ltr);
  });

  testWidgets('Sedi brand lockup stays Sedi. inside English page direction',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        locale: Locale('en'),
        home: Directionality(
          textDirection: TextDirection.ltr,
          child: Scaffold(
            body: Center(
              child: SediBrandLockup(fontSize: 24),
            ),
          ),
        ),
      ),
    );

    final textWidget = tester.widget<Text>(find.text('Sedi.'));
    expect(textWidget.data, 'Sedi.');
    expect(textWidget.textDirection, TextDirection.ltr);
  });

  testWidgets('Sedi brand lockup stays Sedi. inside Arabic page direction',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        locale: Locale('ar'),
        home: Directionality(
          textDirection: TextDirection.rtl,
          child: Scaffold(
            body: Center(
              child: SediBrandLockup(fontSize: 24),
            ),
          ),
        ),
      ),
    );

    final textWidget = tester.widget<Text>(find.text('Sedi.'));
    expect(textWidget.data, 'Sedi.');
    expect(textWidget.textDirection, TextDirection.ltr);
  });

  testWidgets('SediBrainOrb renders without overflow on narrow and normal widths',
      (tester) async {
    for (final width in [280.0, 390.0]) {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: width,
              child: const SediBrainOrb(
                state: Gate3InteractionState.speaking,
              ),
            ),
          ),
        ),
      );

      await tester.pump(const Duration(milliseconds: 32));
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('SediBrainOrb state changes do not throw', (tester) async {
    var state = Gate3InteractionState.idle;

    Future<void> pump() async {
      await tester.pumpWidget(
        MaterialApp(
          home: StatefulBuilder(
            builder: (context, setState) {
              return Scaffold(
                body: Column(
                  children: [
                    SediBrainOrb(state: state),
                    ElevatedButton(
                      onPressed: () => setState(() {
                        final values = Gate3InteractionState.values;
                        state = values[(state.index + 1) % values.length];
                      }),
                      child: const Text('next'),
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 32));
    }

    await pump();
    for (var i = 0; i < Gate3InteractionState.values.length; i++) {
      await tester.tap(find.text('next'));
      await pump();
      expect(tester.takeException(), isNull);
    }
  });
}
