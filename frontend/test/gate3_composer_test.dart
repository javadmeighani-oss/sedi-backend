import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_localization.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/gate3_composer.dart';

void main() {
  Future<void> pumpComposer(
    WidgetTester tester, {
    required bool isRtl,
    required String lang,
    String text = '',
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Directionality(
          textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
          child: Scaffold(
            body: Gate3Composer(
              placeholder: Gate3Localization(lang).composerPlaceholder,
              lang: lang,
              isRtl: isRtl,
              isRecording: false,
              recordingTime: '00:00',
              onSendText: (_) {},
              onStartRecording: () {},
              onStopRecordingAndSend: () {},
            ),
          ),
        ),
      ),
    );
    if (text.isNotEmpty) {
      await tester.enterText(find.byType(TextField), text);
      await tester.pump();
    }
  }

  double leftX(Finder finder, WidgetTester tester) {
    return tester.getTopLeft(finder).dx;
  }

  test('Gate3 composer hint and input font sizes are distinct', () {
    expect(Gate3Composer.hintFontSize, Gate3Composer.baseFontSize * 0.8);
    expect(Gate3Composer.hintFontSize, 12.8);
    expect(Gate3Composer.inputFontSize, closeTo(12.8 * 1.10, 0.001));
    expect(Gate3Composer.inputFontSize, closeTo(14.08, 0.001));
  });

  testWidgets('plus stays on physical left and mic on physical right in RTL',
      (tester) async {
    await pumpComposer(tester, isRtl: true, lang: 'fa');

    final add = find.byIcon(Icons.add_rounded);
    final mic = find.byIcon(Icons.mic_rounded);
    expect(add, findsOneWidget);
    expect(mic, findsOneWidget);
    expect(leftX(add, tester) < leftX(mic, tester), isTrue);
    expect(find.byIcon(Icons.image_outlined), findsNothing);
  });

  testWidgets('plus stays on physical left and mic on physical right in LTR',
      (tester) async {
    await pumpComposer(tester, isRtl: false, lang: 'en');

    final add = find.byIcon(Icons.add_rounded);
    final mic = find.byIcon(Icons.mic_rounded);
    expect(leftX(add, tester) < leftX(mic, tester), isTrue);
    expect(find.byIcon(Icons.image_outlined), findsNothing);
  });

  testWidgets('send replaces mic when text exists on physical right',
      (tester) async {
    await pumpComposer(tester, isRtl: true, lang: 'ar', text: 'hello');

    final add = find.byIcon(Icons.add_rounded);
    final send = find.byIcon(Icons.arrow_upward_rounded);
    expect(find.byIcon(Icons.mic_rounded), findsNothing);
    expect(send, findsOneWidget);
    expect(leftX(add, tester) < leftX(send, tester), isTrue);
  });

  testWidgets('composer applies reduced hint and larger input font sizes',
      (tester) async {
    await pumpComposer(tester, isRtl: false, lang: 'en');

    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.style?.fontSize, Gate3Composer.inputFontSize);
    expect(field.decoration?.hintStyle?.fontSize, Gate3Composer.hintFontSize);
    expect(field.style?.fontSize, closeTo(14.08, 0.001));
    expect(field.decoration?.hintStyle?.fontSize, 12.8);
  });

  testWidgets('attachment menu exposes camera photos and files via plus',
      (tester) async {
    await pumpComposer(tester, isRtl: false, lang: 'en');

    await tester.tap(find.byIcon(Icons.add_rounded));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    final l10n = const Gate3Localization('en');
    expect(find.text(l10n.camera), findsOneWidget);
    expect(find.text(l10n.photos), findsOneWidget);
    expect(find.text(l10n.files), findsOneWidget);
    expect(find.byIcon(Icons.camera_alt_outlined), findsOneWidget);
    expect(find.byIcon(Icons.photo_outlined), findsOneWidget);
    expect(find.byIcon(Icons.attach_file_outlined), findsOneWidget);
  });
}
