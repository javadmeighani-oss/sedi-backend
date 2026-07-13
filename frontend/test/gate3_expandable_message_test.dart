import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/chat/presentation/widgets/expandable_message_content.dart';
import 'package:sedi_app/features/chat/presentation/widgets/message_bubble.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_localization.dart';

void main() {
  const shortText = 'Short message.';
  final longText = List.filled(40, 'word').join(' ');
  final twoLineCandidate =
      'Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda.';

  Widget wrap({
    required Widget child,
    TextDirection direction = TextDirection.ltr,
    Locale locale = const Locale('en'),
  }) {
    return MaterialApp(
      locale: locale,
      home: Directionality(
        textDirection: direction,
        child: Scaffold(
          body: Center(
            child: SizedBox(
              width: 320,
              child: child,
            ),
          ),
        ),
      ),
    );
  }

  Future<Text?> collapsedTextWidget(WidgetTester tester) async {
    final expandable = find.byType(ExpandableMessageContent);
    if (expandable.evaluate().isEmpty) return null;
    return tester.widget<Text>(
      find.descendant(
        of: expandable,
        matching: find.byType(Text),
      ),
    );
  }

  test('default collapsed preview is two rendered lines', () {
    expect(ExpandableMessageContent.defaultCollapsedMaxLines, 2);
  });

  testWidgets('short user message has no expand control', (tester) async {
    await tester.pumpWidget(
      wrap(
        child: MessageBubble(
          messageKey: 'one-line-user',
          message: shortText,
          isSedi: false,
          expandLabel: 'Read more',
          collapseLabel: 'Show less',
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 32));

    expect(find.text('Read more'), findsNothing);
    expect(find.text(shortText), findsOneWidget);
    expect(find.byType(ExpandableMessageContent), findsNothing);
  });

  testWidgets('short assistant message has no expand control', (tester) async {
    await tester.pumpWidget(
      wrap(
        child: MessageBubble(
          messageKey: 'one-line-assistant',
          message: shortText,
          isSedi: true,
          expandLabel: 'Read more',
          collapseLabel: 'Show less',
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 32));

    expect(find.text('Read more'), findsNothing);
    expect(find.text(shortText), findsOneWidget);
    expect(find.byType(ExpandableMessageContent), findsNothing);
  });

  testWidgets('long live user message starts collapsed at two lines',
      (tester) async {
    await tester.pumpWidget(
      wrap(
        child: MessageBubble(
          messageKey: 'long-user',
          message: longText,
          isSedi: false,
          expandLabel: 'Read more',
          collapseLabel: 'Show less',
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 32));

    final textWidget = await collapsedTextWidget(tester);
    expect(textWidget, isNotNull);
    expect(textWidget!.maxLines, 2);
    expect(textWidget.overflow, TextOverflow.ellipsis);
    expect(find.text('Read more'), findsOneWidget);
    expect(find.text(longText), findsOneWidget);
  });

  testWidgets('long user message expands and collapses', (tester) async {
    await tester.pumpWidget(
      wrap(
        child: MessageBubble(
          messageKey: 'long-user-expand',
          message: longText,
          isSedi: false,
          expandLabel: 'Read more',
          collapseLabel: 'Show less',
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 32));

    await tester.tap(find.text('Read more'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 240));

    final expandedText = await collapsedTextWidget(tester);
    expect(expandedText!.maxLines, isNull);
    expect(find.text('Show less'), findsOneWidget);
    expect(find.text(longText), findsOneWidget);

    await tester.tap(find.text('Show less'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 240));

    final collapsedText = await collapsedTextWidget(tester);
    expect(collapsedText!.maxLines, 2);
    expect(collapsedText.overflow, TextOverflow.ellipsis);
    expect(find.text('Read more'), findsOneWidget);
  });

  testWidgets('long assistant response is fully visible without collapse',
      (tester) async {
    await tester.pumpWidget(
      wrap(
        child: MessageBubble(
          messageKey: 'long-assistant',
          message: longText,
          isSedi: true,
          expandLabel: 'Read more',
          collapseLabel: 'Show less',
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 32));

    expect(find.byType(ExpandableMessageContent), findsNothing);
    expect(find.text('Read more'), findsNothing);
    expect(find.text('Show less'), findsNothing);

    final textWidget = tester.widget<Text>(find.text(longText));
    expect(textWidget.maxLines, isNull);
    expect(textWidget.overflow, TextOverflow.clip);
  });

  testWidgets('initial Sedi greeting is fully visible', (tester) async {
    const greeting = 'Hello, I am Sedi. How can I help you today?';
    await tester.pumpWidget(
      wrap(
        child: MessageBubble(
          messageKey: 'greeting',
          message: greeting,
          isSedi: true,
          expandLabel: 'Read more',
          collapseLabel: 'Show less',
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 32));

    expect(find.text(greeting), findsOneWidget);
    expect(find.byType(ExpandableMessageContent), findsNothing);
    expect(find.text('Read more'), findsNothing);
  });

  testWidgets('restored user message follows two-line collapse', (tester) async {
    const historyKey = 'hist-user-42';
    await tester.pumpWidget(
      wrap(
        child: MessageBubble(
          key: const ValueKey(historyKey),
          messageKey: historyKey,
          message: longText,
          isSedi: false,
          expandLabel: 'Read more',
          collapseLabel: 'Show less',
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 32));

    expect(find.byKey(const ValueKey(historyKey)), findsOneWidget);
    expect(find.byKey(const ValueKey('expand-$historyKey')), findsOneWidget);
    final textWidget = await collapsedTextWidget(tester);
    expect(textWidget!.maxLines, 2);
    expect(find.text('Read more'), findsOneWidget);
  });

  testWidgets('restored assistant message remains fully visible', (tester) async {
    const historyKey = 'hist-asst-42';
    await tester.pumpWidget(
      wrap(
        child: MessageBubble(
          key: const ValueKey(historyKey),
          messageKey: historyKey,
          message: longText,
          isSedi: true,
          expandLabel: 'Read more',
          collapseLabel: 'Show less',
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 32));

    expect(find.byKey(const ValueKey(historyKey)), findsOneWidget);
    expect(find.byType(ExpandableMessageContent), findsNothing);
    expect(find.text('Read more'), findsNothing);
    expect(find.text(longText), findsOneWidget);
  });

  testWidgets('fa ar en user expansion labels remain localized', (tester) async {
    const cases = <({String lang, String expand, String collapse})>[
      (lang: 'fa', expand: 'ادامه متن', collapse: 'نمایش کمتر'),
      (lang: 'en', expand: 'Read more', collapse: 'Show less'),
      (lang: 'ar', expand: 'قراءة المزيد', collapse: 'عرض أقل'),
    ];

    for (final c in cases) {
      final l10n = Gate3Localization(c.lang);
      await tester.pumpWidget(
        wrap(
          locale: Locale(c.lang),
          direction: c.lang == 'en' ? TextDirection.ltr : TextDirection.rtl,
          child: MessageBubble(
            messageKey: 'loc-${c.lang}',
            message: longText,
            isSedi: false,
            expandLabel: l10n.readMore,
            collapseLabel: l10n.showLess,
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 32));

      expect(find.text(c.expand), findsOneWidget);
      expect(l10n.readMore, c.expand);
      expect(l10n.showLess, c.collapse);
    }
  });

  testWidgets('duplicate user messages keep independent expansion state',
      (tester) async {
    await tester.pumpWidget(
      wrap(
        child: Column(
          children: [
            MessageBubble(
              key: const ValueKey('dup-a'),
              messageKey: 'dup-a',
              message: longText,
              isSedi: false,
              expandLabel: 'Read more',
              collapseLabel: 'Show less',
            ),
            MessageBubble(
              key: const ValueKey('dup-b'),
              messageKey: 'dup-b',
              message: longText,
              isSedi: false,
              expandLabel: 'Read more',
              collapseLabel: 'Show less',
            ),
          ],
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 32));

    final readMoreButtons = find.text('Read more');
    expect(readMoreButtons, findsNWidgets(2));

    await tester.tap(readMoreButtons.first);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 240));

    expect(find.text('Show less'), findsOneWidget);
    expect(find.text('Read more'), findsOneWidget);
  });

  testWidgets('typing indicator remains outside expandable behavior',
      (tester) async {
    await tester.pumpWidget(
      wrap(
        child: const MessageBubble(
          message: '...',
          isSedi: true,
          showTyping: true,
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 32));

    expect(find.byType(ExpandableMessageContent), findsNothing);
    expect(find.text('Read more'), findsNothing);
  });

  testWidgets('expandable user content renders at narrow width without exceptions',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 280,
            child: ExpandableMessageContent(
              messageKey: 'narrow-1',
              text: longText,
              style: MessageBubble.messageTextStyle,
              expandLabel: 'Read more',
              collapseLabel: 'Show less',
              fadeBaseColor: Colors.white,
              maxContentWidth: MessageBubble.contentMaxWidth,
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 32));
    expect(tester.takeException(), isNull);
  });
}
