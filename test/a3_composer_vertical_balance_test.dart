import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/gate3_composer.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/gate3_composer_action_button.dart';

Gate3Composer _composer({required String placeholder}) {
  return Gate3Composer(
    placeholder: placeholder,
    lang: 'en',
    isRtl: false,
    isRecording: false,
    recordingTime: '00:00',
    onListeningChanged: (_) {},
    onSendText: (_) {},
    onStartRecording: () {},
    onStopRecordingAndSend: () {},
  );
}

void main() {
  testWidgets('empty composer uses +15% vertical geometry without a fixed height',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: _composer(placeholder: 'Talk to Sedi'),
        ),
      ),
    );
    await tester.pump();

    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.style?.fontSize, 16.2);
    expect(field.decoration?.hintStyle?.fontSize, 12.8);
    expect(field.textAlignVertical, TextAlignVertical.top);
    expect(field.minLines, 1);
    expect(field.maxLines, isNull);

    final textBox = tester.widget<ConstrainedBox>(
      find.ancestor(
        of: find.byType(TextField),
        matching: find.byType(ConstrainedBox),
      ).first,
    );
    expect(textBox.constraints.minHeight, 40);
    expect(textBox.constraints.maxHeight, 168);

    final textPad = tester.widget<Padding>(
      find.ancestor(
        of: find.byType(TextField),
        matching: find.byType(Padding),
      ).first,
    );
    expect(textPad.padding, const EdgeInsets.fromLTRB(14, 8, 14, 0));

    final add = tester.widget<Gate3ComposerActionButton>(
      find.widgetWithIcon(Gate3ComposerActionButton, Icons.add_rounded),
    );
    final mic = tester.widget<Gate3ComposerActionButton>(
      find.widgetWithIcon(Gate3ComposerActionButton, Icons.mic_rounded),
    );
    expect(add.size, 36);
    expect(add.iconSize, 22);
    expect(mic.size, 40);
    expect(mic.iconSize, 24);

    final toolbarPad = tester.widget<Padding>(
      find.ancestor(
        of: find.byWidget(add),
        matching: find.byType(Padding),
      ).first,
    );
    expect(toolbarPad.padding, const EdgeInsets.fromLTRB(8, 7, 8, 8));

    final column = tester.widget<Column>(
      find.descendant(
        of: find.byType(Gate3Composer),
        matching: find.byType(Column),
      ).first,
    );
    expect(column.mainAxisSize, MainAxisSize.min);
    expect(find.byType(TextField), findsOneWidget);
  });
}
