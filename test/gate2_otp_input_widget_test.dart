import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/auth_otp/presentation/gate2_otp_input.dart';

void main() {
  testWidgets('OTP paste/autofill enables six-digit completion state', (tester) async {
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

    controller.text = '246810';
    await tester.pump();

    expect(latest, '246810');
    expect(OtpInputHelper.isComplete(controller.text), isTrue);
    expect(find.text('2'), findsOneWidget);
    expect(find.text('0'), findsOneWidget);
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
}
