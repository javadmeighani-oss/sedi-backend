import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/utils/brand_name.dart';
import 'package:sedi_app/features/gate3_interactive/models/gate3_interaction_state.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/gate3_localization.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/gate3_main_icon_row.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/gate3_top_navigation_tray.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_brain_orb.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_horizontal_resonance_visualizer.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_orb_presence.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_presence_tokens.dart';

String _read(String path) => File(path).readAsStringSync();

void main() {
  test('A3 home source: collapsed tray, four destinations, chat Expanded', () {
    final page = _read(
      'lib/features/gate3_interactive/presentation/pages/gate3_interactive_page.dart',
    );
    final orb = _read(
      'lib/features/gate3_interactive/presentation/widgets/sedi_brain_orb.dart',
    );
    final presence = _read(
      'lib/features/gate3_interactive/presentation/widgets/sedi_orb_presence.dart',
    );
    final vis = _read(
      'lib/features/gate3_interactive/presentation/widgets/sedi_horizontal_resonance_visualizer.dart',
    );
    final row = _read(
      'lib/features/gate3_interactive/presentation/widgets/gate3_main_icon_row.dart',
    );

    expect(page.contains('_topTrayExpanded = false'), isTrue);
    expect(page.contains('Gate3TopNavigationTray'), isTrue);
    expect(page.contains('Gate3MainIconRow'), isTrue);
    expect(page.contains('SediOrbPresence'), isTrue);
    expect(page.contains('Expanded('), isTrue);
    expect(page.contains('Gate3Composer'), isTrue);
    expect(page.contains('Gate3ReturnToLatestButton'), isTrue);
    expect(page.contains('Gate3MemoryConsentInvitation'), isTrue);
    expect(page.contains('late final ChatController _controller'), isTrue);
    expect(page.contains('_topTrayExpanded'), isTrue);
    expect(page.contains('sendUserMessage(widget.initialDraft'), isFalse);
    expect(page.contains('Positioned(') && page.contains('SediOrbPresence'), isTrue);
    expect(RegExp(r'Positioned[\s\S]*SediOrbPresence').hasMatch(page), isFalse);

    expect(row.contains('profileTitle'), isTrue);
    expect(row.contains('lifestyle'), isTrue);
    expect(row.contains('gadgets'), isTrue);
    expect(row.contains('notifications'), isTrue);
    expect(row.contains('unreadNotificationCount'), isTrue);
    expect(row.contains('healthCare'), isFalse);

    expect(orb.contains('SediFrequencyRingPainter'), isFalse);
    expect(orb.contains('SediOrbTexturePainter'), isFalse);
    expect(orb.contains('sediOrbBrandLatin'), isTrue);
    expect(orb.contains('0.255'), isTrue);

    expect(
      'SediHorizontalResonanceVisualizer'.allMatches(presence).length,
      1,
    );
    expect(presence.contains('orbBreathingGap'), isFalse);

    expect(vis.contains('barCount = 98'), isTrue);
    expect(vis.contains('amplitudeScale'), isTrue);
    expect(vis.contains('0.80'), isTrue);
    expect(vis.contains('height = SediPresenceTokens.visualizerHeight'), isTrue);
    expect(vis.contains('phaseSpeed = 0.85'), isTrue);

    expect(sediOrbBrandLatin, 'Sedi.');
    expect(SediPresenceTokens.presenceGreen, const Color(0xFF86F83C));
    expect(SediPresenceTokens.amplitudeScale, 0.80);
    expect(SediHorizontalResonanceVisualizer.height, 36);
    expect(SediHorizontalResonanceVisualizer.barCount, 98);
  });

  test('canonical destinations + EN/FA/AR tray labels + RTL', () {
    expect(Gate3Localization('en').isRtl, isFalse);
    expect(Gate3Localization('fa').isRtl, isTrue);
    expect(Gate3Localization('ar').isRtl, isTrue);
    expect(Gate3Localization('en').expandDestinations, isNotEmpty);
    expect(Gate3Localization('fa').expandDestinations, isNotEmpty);
    expect(Gate3Localization('ar').collapseDestinations, isNotEmpty);
    expect(Gate3Localization('en').profileTitle, isNotEmpty);
    expect(Gate3Localization('en').lifestyle, isNotEmpty);
    expect(Gate3Localization('en').gadgets, isNotEmpty);
    expect(Gate3Localization('en').notifications, isNotEmpty);
  });

  test('idle < listening < thinking < speaking; amplitude reduced ~20%', () {
    final idle = SediHorizontalResonanceVisualizer.targetEnergy(
        Gate3InteractionState.idle);
    final listening = SediHorizontalResonanceVisualizer.targetEnergy(
        Gate3InteractionState.listening);
    final thinking = SediHorizontalResonanceVisualizer.targetEnergy(
        Gate3InteractionState.thinking);
    final speaking = SediHorizontalResonanceVisualizer.targetEnergy(
        Gate3InteractionState.speaking);
    expect(idle < listening, isTrue);
    expect(listening < thinking, isTrue);
    expect(thinking < speaking, isTrue);
    expect(SediHorizontalResonanceVisualizer.amplitudeScale, closeTo(0.80, 0.01));
  });

  test('responsive orb diameter is ~25–26% and clamped', () {
    expect(SediBrainOrb.diameterFor(400), closeTo(400 * 0.255, 0.01));
    expect(SediBrainOrb.diameterFor(200), SediBrainOrb.minDiameter);
    expect(SediBrainOrb.diameterFor(800), SediBrainOrb.maxDiameter);
    expect(SediPresenceTokens.barCountFor(400), inInclusiveRange(96, 100));
  });

  testWidgets('tray default collapsed; toggle shows then hides 4 destinations',
      (tester) async {
    var expanded = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: StatefulBuilder(
            builder: (context, setState) {
              return Column(
                children: [
                  Gate3TopNavigationTray(
                    expanded: expanded,
                    onToggle: () => setState(() => expanded = !expanded),
                    expandLabel: 'Show destinations',
                    collapseLabel: 'Hide destinations',
                    child: Gate3MainIconRow(
                      onLifestyle: () {},
                      onGadgets: () {},
                      onNotifications: () {},
                      lang: 'en',
                      unreadNotificationCount: 3,
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
    await tester.pump();
    expect(find.byType(Gate3MainIconRow), findsNothing);
    expect(find.text('Profile'), findsNothing);

    await tester.tap(find.byType(InkWell));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 240));
    expect(find.byType(Gate3MainIconRow), findsOneWidget);
    expect(find.text('Profile'), findsOneWidget);
    expect(find.text('Lifestyle'), findsOneWidget);
    expect(find.text('Gadgets'), findsOneWidget);
    expect(find.text('Notifications'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);

    await tester.tap(find.byType(InkWell).first);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 240));
    expect(find.byType(Gate3MainIconRow), findsNothing);
  });

  testWidgets('collapsed presence is higher and chat is taller than expanded',
      (tester) async {
    var expanded = false;
    late StateSetter setTray;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 390,
            height: 640,
            child: StatefulBuilder(
              builder: (context, setState) {
                setTray = setState;
                return Column(
                  children: [
                    Gate3TopNavigationTray(
                      expanded: expanded,
                      onToggle: () {},
                      expandLabel: 'Show destinations',
                      collapseLabel: 'Hide destinations',
                      child: const SizedBox(height: 72, width: double.infinity),
                    ),
                    const SediOrbPresence(
                      state: Gate3InteractionState.idle,
                      lang: 'en',
                    ),
                    const Expanded(
                      child: ColoredBox(
                        color: Color(0xFFEEEEEE),
                        child: SizedBox.expand(),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    final collapsedPresence = tester.getRect(find.byType(SediOrbPresence));
    final collapsedChat = tester.getRect(find.byType(ColoredBox));

    setTray(() => expanded = true);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 240));
    final expandedPresence = tester.getRect(find.byType(SediOrbPresence));
    final expandedChat = tester.getRect(find.byType(ColoredBox));

    expect(collapsedPresence.top, lessThan(expandedPresence.top));
    expect(collapsedChat.height, greaterThan(expandedChat.height));
  });

  testWidgets('presence renders one visualizer, no ring/texture, Latin Sedi.',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 390,
            child: SediOrbPresence(
              state: Gate3InteractionState.speaking,
              lang: 'fa',
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    expect(find.byType(SediHorizontalResonanceVisualizer), findsOneWidget);
    expect(find.text('Sedi.'), findsOneWidget);
    expect(find.text('صدی'), findsNothing);
    final orb = tester.getSize(find.byType(SediBrainOrb));
    expect(orb.width, inInclusiveRange(92, 104));
    expect(
      tester.getSize(find.byType(SediHorizontalResonanceVisualizer)).height,
      36,
    );
  });
}
