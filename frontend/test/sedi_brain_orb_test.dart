import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/gate3_interactive/models/gate3_interaction_state.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/gate3_vertical_layout.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_audio_visualizer_geometry.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_audio_visualizer_painter.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_brain_orb.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_brand_lockup.dart';

void main() {
  test('SediBrainOrb brand label and official asset path are fixed', () {
    expect(SediBrainOrb.brandLabel, 'Sedi.');
    expect(SediBrandLockup.label, 'Sedi.');
    expect(
      SediBrandLockup.assetPath,
      'assets/images/logo/sedi_logo_1024.png',
    );
    expect(SediBrandLockup.assetPath, isNot(contains('BlendMode')));
    expect(
      SediBrandLockup.assetPath,
      isNot('assets/images/sedi_logo_white.png'),
    );
  });

  test('official wordmark asset is registered in pubspec.yaml', () {
    final pubspec = File('pubspec.yaml').readAsStringSync();
    expect(pubspec, contains('assets/images/logo/'));
    expect(pubspec, contains('assets/images/'));
    expect(SediBrandLockup.assetPath, contains('assets/images/logo/'));
  });

  test('central orb remains 7% smaller and independent from canvas height', () {
    expect(SediBrainOrb.baselineSize, 136);
    expect(SediBrainOrb.scaleFactor, 0.93);
    expect(SediBrainOrb.legacyCoupledExtent, closeTo(136 * 0.93, 0.001));
    expect(SediBrainOrb.orbDiameter, closeTo(136 * 0.93 * 0.72, 0.001));
    expect(
      SediBrainOrb.preferredVisualizerCanvasHeight,
      greaterThan(SediBrainOrb.legacyVisualizerCanvasHeight),
    );
    expect(
      SediBrainOrb.preferredVisualizerCanvasHeight,
      closeTo(
        SediAudioVisualizerGeometry.preferredCanvasHeight(
          SediBrainOrb.orbBodyRadius,
        ),
        0.001,
      ),
    );
    expect(
      SediBrainOrb.preferredVisualizerCanvasHeight -
          SediBrainOrb.legacyVisualizerCanvasHeight,
      inInclusiveRange(24, 42),
    );
  });

  test('geometry includes full glow shader extent in painted outward budget', () {
    final barOnly = SediAudioVisualizerGeometry.radialBarOutwardExtent(
      SediAudioVisualizerGeometry.peakAmplitude,
    );
    final fullExtent = SediAudioVisualizerGeometry.maximumPaintedOutwardExtentAtPeak();
    expect(
      fullExtent,
      barOnly + SediAudioVisualizerGeometry.glowShaderExtraBeyondBarExtension,
    );
    expect(
      fullExtent,
      greaterThanOrEqualTo(
        SediAudioVisualizerGeometry.glowPaintRadiusBeyondSpectrum,
      ),
    );
  });

  test('preferred layout uses full bar and glow on normal widths', () {
    const width = 390.0;
    final canvasHeight = SediBrainOrb.preferredVisualizerCanvasHeight;

    for (final state in Gate3InteractionState.values) {
      final amplitude = SediAudioVisualizerPainter.targetAmplitude(state);
      final layout = SediAudioVisualizerPainter.resolveLayout(
        width: width,
        containerHeight: canvasHeight,
        orbBodyRadius: SediBrainOrb.orbBodyRadius,
        amplitude: amplitude,
      );

      expect(layout.barExtensionFactor, 1.0);
      expect(
        layout.glowPaintRadiusBeyondSpectrum,
        SediAudioVisualizerGeometry.glowPaintRadiusBeyondSpectrum,
      );
      expect(
        layout.glowShaderExtraBeyondBarExtension,
        SediAudioVisualizerGeometry.glowShaderExtraBeyondBarExtension,
      );
      expect(
        SediAudioVisualizerGeometry.paintedExtentFits(
          width: width,
          containerHeight: canvasHeight,
          layout: layout,
          amplitude: amplitude,
        ),
        isTrue,
        reason: 'state=$state',
      );
    }
  });

  test('width 120 fits without clipping at preferred canvas height', () {
    const width = 120.0;
    final canvasHeight = SediBrainOrb.preferredVisualizerCanvasHeight;

    expect(
      () => SediAudioVisualizerPainter.resolveLayout(
        width: width,
        containerHeight: canvasHeight,
        orbBodyRadius: SediBrainOrb.orbBodyRadius,
      ),
      returnsNormally,
    );

    final layout = SediAudioVisualizerPainter.resolveLayout(
      width: width,
      containerHeight: canvasHeight,
      orbBodyRadius: SediBrainOrb.orbBodyRadius,
      amplitude: SediAudioVisualizerGeometry.peakAmplitude,
    );

    expect(layout.spectrumRadius, isFinite);
    expect(layout.spectrumRadius, greaterThan(0));
    expect(layout.barExtensionFactor, inInclusiveRange(0.0, 1.0));
    expect(layout.glowPaintRadiusBeyondSpectrum, inInclusiveRange(0.0, 6.0));
    expect(layout.glowShaderExtraBeyondBarExtension, inInclusiveRange(0.0, 4.0));

    expect(
      SediAudioVisualizerGeometry.paintedExtentFits(
        width: width,
        containerHeight: canvasHeight,
        layout: layout,
        amplitude: SediAudioVisualizerGeometry.peakAmplitude,
      ),
      isTrue,
    );
  });

  test('Gate3VerticalLayout reallocates height from message viewport budget', () {
    const normalPhoneSafeHeight = 720.0;
    final resolved = Gate3VerticalLayout.resolveVisualizerCanvasHeight(
      availableSafeHeight: normalPhoneSafeHeight,
      orbBodyRadius: SediBrainOrb.orbBodyRadius,
    );

    expect(resolved, SediBrainOrb.preferredVisualizerCanvasHeight);
    expect(
      resolved - SediBrainOrb.legacyVisualizerCanvasHeight,
      inInclusiveRange(24, 42),
    );
  });

  test('Gate3VerticalLayout preserves composer minimum on short screens', () {
    final resolved = Gate3VerticalLayout.resolveVisualizerCanvasHeight(
      availableSafeHeight: 420,
      orbBodyRadius: SediBrainOrb.orbBodyRadius,
    );

    expect(resolved, isFinite);
    expect(resolved, greaterThan(SediBrainOrb.orbDiameter));
    expect(resolved, lessThan(SediBrainOrb.preferredVisualizerCanvasHeight));
    expect(
      Gate3VerticalLayout.composerMinimumHeight,
      108,
    );
  });

  test('spectrum radius resolves inside layout bounds', () {
    final radius = SediAudioVisualizerPainter.resolveSpectrumRadius(
      width: 320,
      containerHeight: SediBrainOrb.preferredVisualizerCanvasHeight,
      orbBodyRadius: SediBrainOrb.orbBodyRadius,
    );
    expect(radius, greaterThan(SediBrainOrb.orbBodyRadius));
    expect(radius, lessThan(320 / 2));
  });

  testWidgets('official transparent wordmark image is used without blend workaround',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Directionality(
          textDirection: TextDirection.rtl,
          child: Scaffold(
            body: Center(
              child: SediBrandLockup(height: 24),
            ),
          ),
        ),
      ),
    );

    expect(find.byType(Image), findsOneWidget);
    expect(find.byType(ColorFiltered), findsNothing);
    expect(find.text('Sedi.'), findsNothing);

    final image = tester.widget<Image>(find.byType(Image));
    expect(image.matchTextDirection, isFalse);
    expect(
      image.image,
      const AssetImage('assets/images/logo/sedi_logo_1024.png'),
    );

    final semantics = tester.getSemantics(find.byType(SediBrandLockup));
    expect(semantics.label, 'Sedi.');
  });

  testWidgets('Sedi brand lockup stays LTR isolated under RTL parent',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Directionality(
          textDirection: TextDirection.rtl,
          child: Scaffold(
            body: Center(
              child: SediBrandLockup(height: 24),
            ),
          ),
        ),
      ),
    );

    final lockupDirectionality = tester.widget<Directionality>(
      find.descendant(
        of: find.byType(SediBrandLockup),
        matching: find.byWidgetPredicate(
          (widget) =>
              widget is Directionality &&
              widget.textDirection == TextDirection.ltr,
        ),
      ),
    );
    expect(lockupDirectionality.textDirection, TextDirection.ltr);
  });

  testWidgets('SediBrainOrb uses explicit canvas height without overflow',
      (tester) async {
    final canvasHeight = SediBrainOrb.preferredVisualizerCanvasHeight;

    for (final width in [120.0, 220.0, 280.0, 390.0]) {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: width,
              child: SediBrainOrb(
                state: Gate3InteractionState.speaking,
                canvasHeight: canvasHeight,
              ),
            ),
          ),
        ),
      );

      await tester.pump(const Duration(milliseconds: 32));
      expect(tester.takeException(), isNull);

      final sizedBoxes = tester.widgetList<SizedBox>(
        find.descendant(
          of: find.byType(SediBrainOrb),
          matching: find.byWidgetPredicate(
            (widget) => widget is SizedBox && widget.height == canvasHeight,
          ),
        ),
      );
      expect(sizedBoxes, isNotEmpty);
    }
  });

  testWidgets('SediBrainOrb state changes do not throw', (tester) async {
    var state = Gate3InteractionState.idle;

    Future<void> pump() async {
      await tester.pumpWidget(
        MaterialApp(
          home: StatefulBuilder(
            builder: (context, setState) {
              return Scaffold(
                body: Column(
                  children: [
                    SediBrainOrb(
                      state: state,
                      canvasHeight: SediBrainOrb.preferredVisualizerCanvasHeight,
                    ),
                    ElevatedButton(
                      onPressed: () => setState(() {
                        final values = Gate3InteractionState.values;
                        state = values[(state.index + 1) % values.length];
                      }),
                      child: const Text('next'),
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 32));
    }

    await pump();
    for (var i = 0; i < Gate3InteractionState.values.length; i++) {
      await tester.tap(find.text('next'));
      await pump();
      expect(tester.takeException(), isNull);
    }
  });
}
