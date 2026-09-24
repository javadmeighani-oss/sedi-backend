import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/chat/presentation/widgets/message_bubble.dart';

String _read(String path) => File(path).readAsStringSync();

Finder _decoratedUserBubble() {
  return find.byWidgetPredicate(
    (w) => w is Container && w.decoration is BoxDecoration,
  );
}

void main() {
  test('edit icon is outside the decorated user bubble in source', () {
    final bubble = _read(
      'lib/features/chat/presentation/widgets/message_bubble.dart',
    );
    expect(bubble.contains('Icons.edit_outlined'), isTrue);
    expect(bubble.contains('Tooltip('), isTrue);
    expect(bubble.contains("editLabel ?? 'Edit'"), isTrue);
    expect(bubble.contains('widget.onEdit'), isTrue);
    expect(bubble.contains('Edit icon sits outside'), isTrue);
    expect(bubble.contains('Read more'), isTrue);
    expect(bubble.contains('Read less'), isTrue);
    expect(bubble.contains('Tap to retry'), isTrue);
    expect(bubble.contains('AlignmentDirectional.centerEnd'), isTrue);
    expect(bubble.contains('AlignmentDirectional.centerStart'), isTrue);

    final bubbleBlock = RegExp(
      r'decoration: BoxDecoration\([\s\S]*?child: body,',
    ).firstMatch(bubble)?.group(0);
    expect(bubbleBlock, isNotNull);
    expect(bubbleBlock!.contains('Icons.edit_outlined'), isFalse);
    expect(bubble.contains('if (editAction != null)'), isTrue);
    expect(bubble.contains('width: 44'), isTrue);
    expect(bubble.contains('height: 44'), isTrue);
    expect(bubble.contains('size: 16'), isTrue);

    final page = _read(
      'lib/features/gate3_interactive/presentation/pages/gate3_interactive_page.dart',
    );
    expect(page.contains('_scrollToBottom'), isTrue);
    expect(page.contains('Gate3ReturnToLatestButton'), isTrue);
    expect(page.contains('Gate3Composer'), isTrue);
    expect(page.contains('ScrollController'), isTrue);

    final composer = _read(
      'lib/features/gate3_interactive/presentation/widgets/gate3_composer.dart',
    );
    expect(composer.contains('onSendText'), isTrue);
    final chat = _read('lib/features/chat/state/chat_controller.dart');
    expect(chat.contains('class ChatController'), isTrue);
  });

  testWidgets('user edit icon is outside bubble; assistant has none',
      (tester) async {
    var taps = 0;
    const long =
        'This user message is long enough to collapse because it exceeds one hundred and twenty characters easily.';
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              MessageBubble(
                message: 'Short user text',
                isSedi: false,
                onEdit: () => taps++,
                editLabel: 'Edit',
              ),
              MessageBubble(
                message: long,
                isSedi: false,
                onEdit: () {},
                editLabel: 'Edit',
              ),
              const MessageBubble(
                message: 'Assistant reply',
                isSedi: true,
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byIcon(Icons.edit_outlined), findsNWidgets(2));
    expect(find.text('Edit'), findsNothing);
    expect(find.text('ویرایش'), findsNothing);
    expect(find.byType(Tooltip), findsWidgets);
    expect(find.text('Read more'), findsOneWidget);
    expect(find.text('Read less'), findsNothing);
    expect(
      find.descendant(
        of: _decoratedUserBubble().first,
        matching: find.byIcon(Icons.edit_outlined),
      ),
      findsNothing,
    );

    await tester.tap(find.byIcon(Icons.edit_outlined).first);
    await tester.pump();
    expect(taps, 1);
    final editHit = find.ancestor(
      of: find.byIcon(Icons.edit_outlined).first,
      matching: find.byWidgetPredicate(
        (w) => w is SizedBox && w.width == 44 && w.height == 44,
      ),
    );
    expect(editHit, findsOneWidget);
    expect(tester.getSize(editHit), const Size(44, 44));

    final assistant = find.ancestor(
      of: find.text('Assistant reply'),
      matching: find.byType(MessageBubble),
    );
    expect(
      find.descendant(
        of: assistant,
        matching: find.byIcon(Icons.edit_outlined),
      ),
      findsNothing,
    );
  });

  testWidgets('RTL and LTR keep user alignment at directional end',
      (tester) async {
    Future<void> pumpDir(TextDirection dir) {
      return tester.pumpWidget(
        MaterialApp(
          home: Directionality(
            textDirection: dir,
            child: MessageBubble(
              message: 'Hello',
              isSedi: false,
              onEdit: () {},
              editLabel: 'Edit',
            ),
          ),
        ),
      );
    }

    await pumpDir(TextDirection.ltr);
    await tester.pump();
    final ltrBubble = tester.widget<Align>(
      find.descendant(
        of: find.byType(MessageBubble),
        matching: find.byType(Align).first,
      ),
    );
    expect(ltrBubble.alignment, AlignmentDirectional.centerEnd);
    expect(find.byIcon(Icons.edit_outlined), findsOneWidget);

    await pumpDir(TextDirection.rtl);
    await tester.pump();
    final rtlBubble = tester.widget<Align>(
      find.descendant(
        of: find.byType(MessageBubble),
        matching: find.byType(Align).first,
      ),
    );
    expect(rtlBubble.alignment, AlignmentDirectional.centerEnd);
    expect(find.byIcon(Icons.edit_outlined), findsOneWidget);
    expect(find.text('Edit'), findsNothing);
  });
}
