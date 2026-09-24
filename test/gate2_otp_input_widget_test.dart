import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_otp_input.dart';

void main() {
  testWidgets('OTP paste/autofill enables six-digit completion state',
      (tester) async {
    final controller = TextEditingController();
    final focusNode = FocusNode();

    addTearDown(controller.dispose);
    addTearDown(focusNode.dispose);

    var latest = '';
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Gate2OtpInput(
            controller: controller,
            focusNode: focusNode,
            onChanged: (value) => latest = value,
          ),
        ),
      ),
    );
    await tester.pump();

    controller.text = '246810';
    await tester.pump();

    expect(latest, '246810');
    expect(OtpInputHelper.isComplete(controller.text), isTrue);
    expect(find.text('2'), findsOneWidget);
    expect(find.text('0'), findsOneWidget);
  });

  testWidgets('manual ASCII sequential typing renders boxes LTR',
      (tester) async {
    final controller = TextEditingController();
    final focusNode = FocusNode();
    addTearDown(controller.dispose);
    addTearDown(focusNode.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Gate2OtpInput(
            controller: controller,
            focusNode: focusNode,
          ),
        ),
      ),
    );
    await tester.pump();

    await tester.tap(find.byType(Gate2OtpInput));
    await tester.pump();
    expect(focusNode.hasFocus, isTrue);

    await tester.enterText(find.byType(TextField), '1');
    await tester.pump();
    expect(controller.text, '1');
    expect(
      find.byWidgetPredicate((w) => w is Text && w.data == '1'),
      findsOneWidget,
    );

    await tester.enterText(find.byType(TextField), '12');
    await tester.pump();
    expect(controller.text, '12');

    await tester.enterText(find.byType(TextField), '123456');
    await tester.pump();
    expect(controller.text, '123456');
    expect(OtpInputHelper.isComplete(controller.text), isTrue);
    expect(
      find.byWidgetPredicate((w) => w is Text && w.data == '6'),
      findsOneWidget,
    );

    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.autofillHints, contains(AutofillHints.oneTimeCode));
    expect(field.keyboardType, TextInputType.number);
  });

  testWidgets('Persian manual input normalizes to ASCII in boxes',
      (tester) async {
    final controller = TextEditingController();
    final focusNode = FocusNode();
    addTearDown(controller.dispose);
    addTearDown(focusNode.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Gate2OtpInput(
            controller: controller,
            focusNode: focusNode,
          ),
        ),
      ),
    );
    await tester.pump();

    await tester.enterText(find.byType(TextField), '۱۲۳۴۵۶');
    await tester.pump();

    expect(controller.text, '123456');
    expect(find.text('1'), findsOneWidget);
    expect(find.text('۶'), findsNothing);
    expect(find.text('6'), findsOneWidget);
  });

  testWidgets('Arabic-Indic manual input normalizes to ASCII', (tester) async {
    final controller = TextEditingController();
    final focusNode = FocusNode();
    addTearDown(controller.dispose);
    addTearDown(focusNode.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Gate2OtpInput(
            controller: controller,
            focusNode: focusNode,
          ),
        ),
      ),
    );
    await tester.pump();

    await tester.enterText(find.byType(TextField), '١٢٣٤٥٦');
    await tester.pump();
    expect(controller.text, '123456');
  });

  testWidgets('backspace shortens ASCII code', (tester) async {
    final controller = TextEditingController(text: '123456');
    final focusNode = FocusNode();
    addTearDown(controller.dispose);
    addTearDown(focusNode.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Gate2OtpInput(
            controller: controller,
            focusNode: focusNode,
          ),
        ),
      ),
    );
    await tester.pump();

    await tester.enterText(find.byType(TextField), '12345');
    await tester.pump();
    expect(controller.text, '12345');
    expect(OtpInputHelper.isComplete(controller.text), isFalse);
  });

  testWidgets('paste six mixed digits becomes ASCII', (tester) async {
    final controller = TextEditingController();
    final focusNode = FocusNode();
    addTearDown(controller.dispose);
    addTearDown(focusNode.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Gate2OtpInput(
            controller: controller,
            focusNode: focusNode,
          ),
        ),
      ),
    );
    await tester.pump();

    await tester.enterText(find.byType(TextField), '12۳٤5۶');
    await tester.pump();
    expect(controller.text, '123456');
  });

  testWidgets('OTP row is LTR Directionality', (tester) async {
    final controller = TextEditingController(text: '123456');
    final focusNode = FocusNode();
    addTearDown(controller.dispose);
    addTearDown(focusNode.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Gate2OtpInput(
            controller: controller,
            focusNode: focusNode,
          ),
        ),
      ),
    );
    await tester.pump();

    final dir = tester.widget<Directionality>(
      find
          .descendant(
            of: find.byType(Gate2OtpInput),
            matching: find.byType(Directionality),
          )
          .first,
    );
    expect(dir.textDirection, TextDirection.ltr);
  });

  testWidgets('OTP row fits narrow width without overflow', (tester) async {
    final controller = TextEditingController();
    final focusNode = FocusNode();

    addTearDown(controller.dispose);
    addTearDown(focusNode.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: const MediaQueryData(size: Size(280, 640)),
          child: Scaffold(
            body: Center(
              child: SizedBox(
                width: 248,
                child: Gate2OtpInput(
                  controller: controller,
                  focusNode: focusNode,
                ),
              ),
            ),
          ),
        ),
      ),
    );

    controller.text = '123456';
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('1'), findsOneWidget);
    expect(find.text('6'), findsOneWidget);
  });

  testWidgets('tapping a filled slot activates it without truncating later digits',
      (tester) async {
    final controller = TextEditingController(text: '123456');
    final focusNode = FocusNode();
    addTearDown(controller.dispose);
    addTearDown(focusNode.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Gate2OtpInput(
            controller: controller,
            focusNode: focusNode,
          ),
        ),
      ),
    );
    await tester.pump();
    focusNode.unfocus();
    await tester.pump();
    expect(focusNode.hasFocus, isFalse);

    await tester.tap(find.byKey(const ValueKey('a2-otp-slot-2')));
    await tester.pump();

    expect(focusNode.hasFocus, isTrue);
    expect(controller.text, '123456');
    expect(find.text('3'), findsOneWidget);
    expect(find.text('6'), findsOneWidget);
    expect(controller.selection.start, 2);
    expect(controller.selection.end, 3);
    expect(find.byType(OtpSlotCaret), findsOneWidget);
  });

  testWidgets('active filled slot shows olive caret', (tester) async {
    final controller = TextEditingController(text: '12');
    final focusNode = FocusNode();
    addTearDown(controller.dispose);
    addTearDown(focusNode.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Gate2OtpInput(
            controller: controller,
            focusNode: focusNode,
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('a2-otp-slot-0')));
    await tester.pump();

    expect(find.byType(OtpSlotCaret), findsOneWidget);
    expect(controller.text, '12');
    expect(find.text('1'), findsOneWidget);
    expect(find.text('2'), findsOneWidget);
  });
}
