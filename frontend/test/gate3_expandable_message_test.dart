import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/chat/presentation/widgets/expandable_message_content.dart';
import 'package:sedi_app/features/chat/presentation/widgets/message_bubble.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_localization.dart';

void main() {
  const shortText = 'Short message.';
  final longText = List.filled(40, 'word').join(' ');

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

  testWidgets('short messages do not show Read more', (tester) async {
    await tester.pumpWidget(
      wrap(
        child: MessageBubble(
          messageKey: 'short-1',
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
  });

  testWidgets('long user and Sedi messages expand and collapse', (tester) async {
    for (final isSedi in [false, true]) {
      await tester.pumpWidget(
        wrap(
          child: MessageBubble(
            messageKey: 'long-${isSedi ? 'sedi' : 'user'}',
            message: longText,
            isSedi: isSedi,
            expandLabel: 'Read more',
            collapseLabel: 'Show less',
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 32));

      expect(find.text('Read more'), findsOneWidget);

      await tester.tap(find.text('Read more'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 240));

      expect(find.text('Show less'), findsOneWidget);
      expect(find.text(longText), findsOneWidget);

      await tester.tap(find.text('Show less'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 240));

      expect(find.text('Read more'), findsOneWidget);
    }
  });

  testWidgets('fa ar en expansion labels are localized', (tester) async {
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
            isSedi: true,
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

  testWidgets('duplicate text messages keep independent expansion state',
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
              isSedi: true,
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

  testWidgets('restored history messages use stable keys', (tester) async {
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
    expect(find.byKey(const ValueKey('expand-$historyKey')), findsOneWidget);
  });

  testWidgets('expandable content renders at narrow width without exceptions',
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
