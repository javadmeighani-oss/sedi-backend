import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/gate3_return_to_latest_button.dart';

class _StubScrollController extends ScrollController {
  _StubScrollController(this._held);

  final List<ScrollPosition> _held;

  @override
  Iterable<ScrollPosition> get positions => _held;
}

class _StubScrollPosition extends Fake implements ScrollPosition {
  _StubScrollPosition({
    required this.hasContentDimensions,
    this.maxScrollExtent = 0,
    this.pixels = 0,
  });

  @override
  final bool hasContentDimensions;

  @override
  final double maxScrollExtent;

  @override
  final double pixels;
}

Finder _latestIcon() => find.byIcon(Icons.keyboard_arrow_down_rounded);

Future<void> _pumpButton(
  WidgetTester tester,
  ScrollController controller,
) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Stack(
          children: [
            const ColoredBox(color: Color(0xFFFFFFFF)),
            Positioned(
              right: 12,
              bottom: 12,
              child: Gate3ReturnToLatestButton(
                scrollController: controller,
                onTap: () {},
                tooltip: 'Latest',
              ),
            ),
          ],
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets('A) unattached controller: no throw, button hidden',
      (tester) async {
    final controller = ScrollController();
    addTearDown(controller.dispose);
    await _pumpButton(tester, controller);
    expect(tester.takeException(), isNull);
    expect(find.byType(ErrorWidget), findsNothing);
    expect(_latestIcon(), findsNothing);
    expect(gate3SingleReadyScrollPosition(controller), isNull);
  });

  testWidgets(
      'B/E) attached position before content dimensions: no throw, hidden, no ErrorWidget',
      (tester) async {
    final controller = _StubScrollController([
      _StubScrollPosition(hasContentDimensions: false),
    ]);
    await _pumpButton(tester, controller);
    expect(tester.takeException(), isNull);
    expect(find.byType(ErrorWidget), findsNothing);
    expect(_latestIcon(), findsNothing);
    expect(gate3SingleReadyScrollPosition(controller), isNull);
  });

  testWidgets('C) exactly one ready position near latest: hidden',
      (tester) async {
    final controller = _StubScrollController([
      _StubScrollPosition(
        hasContentDimensions: true,
        maxScrollExtent: 240,
        pixels: 240,
      ),
    ]);
    await _pumpButton(tester, controller);
    expect(tester.takeException(), isNull);
    expect(find.byType(ErrorWidget), findsNothing);
    expect(_latestIcon(), findsNothing);
    expect(gate3SingleReadyScrollPosition(controller), isNotNull);
  });

  testWidgets('D) exactly one ready position >72 from latest: visible',
      (tester) async {
    final controller = _StubScrollController([
      _StubScrollPosition(
        hasContentDimensions: true,
        maxScrollExtent: 240,
        pixels: 160,
      ),
    ]);
    await _pumpButton(tester, controller);
    expect(tester.takeException(), isNull);
    expect(find.byType(ErrorWidget), findsNothing);
    expect(_latestIcon(), findsOneWidget);
    final pos = gate3SingleReadyScrollPosition(controller)!;
    expect(pos.maxScrollExtent - pos.pixels, greaterThan(72));
  });

  test('single-position and content-dimension guards hide unsafe states', () {
    expect(
      gate3SingleReadyScrollPosition(ScrollController()),
      isNull,
    );
    expect(
      gate3SingleReadyScrollPosition(
        _StubScrollController([
          _StubScrollPosition(hasContentDimensions: false),
          _StubScrollPosition(hasContentDimensions: true, maxScrollExtent: 10),
        ]),
      ),
      isNull,
    );
    expect(
      gate3SingleReadyScrollPosition(
        _StubScrollController([
          _StubScrollPosition(hasContentDimensions: true, maxScrollExtent: 80, pixels: 0),
        ]),
      ),
      isNotNull,
    );
  });

  testWidgets('threshold 72 is preserved: equal to 72 stays hidden',
      (tester) async {
    final atThreshold = _StubScrollController([
      _StubScrollPosition(
        hasContentDimensions: true,
        maxScrollExtent: 172,
        pixels: 100,
      ),
    ]);
    await _pumpButton(tester, atThreshold);
    expect(_latestIcon(), findsNothing);

    final justOver = _StubScrollController([
      _StubScrollPosition(
        hasContentDimensions: true,
        maxScrollExtent: 173,
        pixels: 100,
      ),
    ]);
    await _pumpButton(tester, justOver);
    expect(_latestIcon(), findsOneWidget);
  });
}
