import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/gate3_message_viewport.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/gate3_return_to_latest_button.dart';

void main() {
  Widget buildHarness({
    required ScrollController controller,
    required VoidCallback onReturn,
    bool isRtl = false,
    EdgeInsets viewInsets = EdgeInsets.zero,
    int itemCount = 30,
  }) {
    return MaterialApp(
      home: MediaQuery(
        data: MediaQueryData(viewInsets: viewInsets),
        child: Directionality(
          textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
          child: Scaffold(
            body: SizedBox(
              height: 400,
              width: 360,
              child: Gate3MessageViewport(
                scrollController: controller,
                onReturnToLatest: onReturn,
                returnTooltip: 'Latest',
                child: ListView.builder(
                  controller: controller,
                  reverse: true,
                  itemCount: itemCount,
                  itemBuilder: (context, index) => SizedBox(
                    height: 48,
                    child: Center(child: Text('message-$index')),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Finder laneFinder() {
    return find.descendant(
      of: find.byType(Gate3MessageViewport),
      matching: find.byType(AnimatedContainer),
    );
  }

  double laneHeight(WidgetTester tester) {
    final finder = laneFinder();
    if (finder.evaluate().isEmpty) return 0;
    return tester.getSize(finder).height;
  }

  test('shouldShowReturnButton requires an attached scroll controller', () {
    final controller = ScrollController(initialScrollOffset: 120);
    expect(Gate3MessageViewport.shouldShowReturnButton(controller), isFalse);
    controller.dispose();
  });

  testWidgets('button hidden at reverse-list offset <= 72', (tester) async {
    final controller = ScrollController(initialScrollOffset: 60);
    addTearDown(controller.dispose);

    await tester.pumpWidget(buildHarness(controller: controller, onReturn: () {}));
    await tester.pump();

    expect(Gate3MessageViewport.shouldShowReturnButton(controller), isFalse);
    expect(laneHeight(tester), 0);
    expect(find.byType(Gate3ReturnToLatestButton), findsNothing);
  });

  testWidgets('button visible above reverse-list threshold', (tester) async {
    final controller = ScrollController(initialScrollOffset: 120);
    addTearDown(controller.dispose);

    await tester.pumpWidget(buildHarness(controller: controller, onReturn: () {}));
    await tester.pump();

    expect(Gate3MessageViewport.shouldShowReturnButton(controller), isTrue);
  });

  testWidgets('full viewport is used while return button is hidden',
      (tester) async {
    final controller = ScrollController();
    addTearDown(controller.dispose);

    await tester.pumpWidget(buildHarness(controller: controller, onReturn: () {}));
    await tester.pump();

    expect(laneHeight(tester), 0);
    expect(find.byType(Gate3ReturnToLatestButton), findsNothing);
  });

  testWidgets('56px lane is reserved while return button is visible',
      (tester) async {
    final controller = ScrollController(initialScrollOffset: 120);
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      buildHarness(controller: controller, onReturn: () {}),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    expect(laneHeight(tester), closeTo(Gate3MessageViewport.reservedLaneHeight, 0.5));
    expect(find.byType(Gate3ReturnToLatestButton), findsOneWidget);
  });

  testWidgets('message viewport bottom does not overlap the return button',
      (tester) async {
    final controller = ScrollController(initialScrollOffset: 120);
    addTearDown(controller.dispose);

    await tester.pumpWidget(buildHarness(controller: controller, onReturn: () {}));
    await tester.pump();
    await tester.pumpAndSettle();

    final listBottom = tester.getBottomLeft(find.byType(ListView));
    final laneTop = tester.getTopLeft(laneFinder());
    final laneSize = tester.getSize(laneFinder());
    final buttonRect = tester.getRect(find.byType(Gate3ReturnToLatestButton));

    expect(laneSize.height, closeTo(Gate3MessageViewport.reservedLaneHeight, 0.5));
    expect(listBottom.dy, lessThanOrEqualTo(laneTop.dy + 0.5));
    expect(buttonRect.width, closeTo(Gate3ReturnToLatestButton.size, 0.5));
    expect(buttonRect.height, closeTo(Gate3ReturnToLatestButton.size, 0.5));
    expect(buttonRect.bottom, lessThanOrEqualTo(laneTop.dy + laneSize.height + 0.5));
    expect(buttonRect.top, greaterThanOrEqualTo(laneTop.dy - 0.5));
  });

  testWidgets('return button stays physical-right in RTL', (tester) async {
    final controller = ScrollController(initialScrollOffset: 120);
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      buildHarness(controller: controller, onReturn: () {}, isRtl: true),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    final viewportRect = tester.getRect(find.byType(Gate3MessageViewport));
    final buttonRect = tester.getRect(find.byType(Gate3ReturnToLatestButton));

    expect(
      buttonRect.right,
      closeTo(viewportRect.right - Gate3MessageViewport.buttonInsetRight, 1.0),
    );
    expect(
      buttonRect.left,
      greaterThan(viewportRect.left + viewportRect.width / 2),
    );
  });

  testWidgets('tap invokes return callback and hides lane at offset zero',
      (tester) async {
    final controller = ScrollController(initialScrollOffset: 120);
    addTearDown(controller.dispose);
    var tapped = false;

    await tester.pumpWidget(
      buildHarness(controller: controller, onReturn: () => tapped = true),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    await tester.tap(find.byType(Gate3ReturnToLatestButton));
    await tester.pump();

    expect(tapped, isTrue);

    await controller.animateTo(
      0,
      duration: const Duration(milliseconds: 280),
      curve: Curves.easeOutCubic,
    );
    await tester.pumpAndSettle();

    expect(laneHeight(tester), 0);
    expect(find.byType(Gate3ReturnToLatestButton), findsNothing);
  });

  testWidgets('keyboard viewInsets do not move button to logical left',
      (tester) async {
    final controller = ScrollController(initialScrollOffset: 120);
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      buildHarness(
        controller: controller,
        onReturn: () {},
        isRtl: true,
        viewInsets: const EdgeInsets.only(bottom: 280),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    final viewportRect = tester.getRect(find.byType(Gate3MessageViewport));
    final buttonRect = tester.getRect(find.byType(Gate3ReturnToLatestButton));

    expect(
      buttonRect.right,
      closeTo(viewportRect.right - Gate3MessageViewport.buttonInsetRight, 1.0),
    );
    expect(laneHeight(tester), closeTo(Gate3MessageViewport.reservedLaneHeight, 0.5));
  });
}
