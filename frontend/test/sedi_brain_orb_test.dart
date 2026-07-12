import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/gate3_interactive/logic/procedural_voice_waveform.dart';
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
    expect(
      SediBrainOrb.preferredVisualizerCanvasHeight,
      closeTo(164.83, 0.1),
    );
  });

  test('wordmark is exactly 80% of previous rendered size', () {
    const previousRatio = 0.34;
    expect(SediBrainOrb.brandHeightRatio, closeTo(previousRatio * 0.8, 0.0001));
    expect(SediBrainOrb.brandHeightRatio, 0.272);

    final brandHeight = SediBrainOrb.orbDiameter * SediBrainOrb.brandHeightRatio;
    final previousBrandHeight = SediBrainOrb.orbDiameter * previousRatio;
    expect(brandHeight, closeTo(previousBrandHeight * 0.8, 0.0001));
  });

  test('circular profile is state-independent', () {
    final idleLayout = SediAudioVisualizerPainter.resolveLayout(
      width: 390,
      containerHeight: SediBrainOrb.preferredVisualizerCanvasHeight,
      orbBodyRadius: SediBrainOrb.orbBodyRadius,
    );

    for (final state in Gate3InteractionState.values) {
      expect(
        SediAudioVisualizerPainter.targetAmplitude(state),
        SediCircularEqualizerProfile.amplitude,
      );
      expect(
        SediAudioVisualizerPainter.targetGlow(state),
        SediCircularEqualizerProfile.glow,
      );
      expect(
        SediAudioVisualizerPainter.circularPhaseSpeed(state),
        SediCircularEqualizerProfile.phaseSpeed,
      );

      final layout = SediAudioVisualizerPainter.resolveLayout(
        width: 390,
        containerHeight: SediBrainOrb.preferredVisualizerCanvasHeight,
        orbBodyRadius: SediBrainOrb.orbBodyRadius,
      );

      expect(layout.spectrumRadius, idleLayout.spectrumRadius);
      expect(layout.barExtensionFactor, idleLayout.barExtensionFactor);
      expect(
        layout.glowPaintRadiusBeyondSpectrum,
        idleLayout.glowPaintRadiusBeyondSpectrum,
      );
      expect(
        layout.glowShaderExtraBeyondBarExtension,
        idleLayout.glowShaderExtraBeyondBarExtension,
      );
    }
  });

  test('horizontal energy ordering follows idle < listening < thinking << speaking',
      () {
    final idle = SediAudioVisualizerPainter.targetHorizontalEnergy(
      Gate3InteractionState.idle,
    );
    final listening = SediAudioVisualizerPainter.targetHorizontalEnergy(
      Gate3InteractionState.listening,
    );
    final thinking = SediAudioVisualizerPainter.targetHorizontalEnergy(
      Gate3InteractionState.thinking,
    );
    final speaking = SediAudioVisualizerPainter.targetHorizontalEnergy(
      Gate3InteractionState.speaking,
    );

    expect(idle, lessThan(0.1));
    expect(listening, lessThan(thinking));
    expect(listening - idle, lessThan(0.08));
    expect(thinking, greaterThan(idle * 3));
    expect(speaking, greaterThan(thinking * 2));
    expect(speaking, greaterThan(0.7));
  });

  test('horizontal procedural waveform is deterministic and asymmetric', () {
    const x = 0.42;
    const time = 0.31;
    const energy = 0.8;

    final leftA = ProceduralVoiceWaveform.horizontalPeakAmplitude(
      normalizedX: x,
      time: time,
      energy: energy,
      state: Gate3InteractionState.speaking,
      isRightSide: false,
    );
    final leftB = ProceduralVoiceWaveform.horizontalPeakAmplitude(
      normalizedX: x,
      time: time,
      energy: energy,
      state: Gate3InteractionState.speaking,
      isRightSide: false,
    );
    final right = ProceduralVoiceWaveform.horizontalPeakAmplitude(
      normalizedX: x,
      time: time,
      energy: energy,
      state: Gate3InteractionState.speaking,
      isRightSide: true,
    );

    expect(leftA.isFinite, isTrue);
    expect(leftA, closeTo(leftB, 0.000001));
    expect(right, isNot(closeTo(leftA, 0.000001)));

    final lowerLeft = ProceduralVoiceWaveform.asymmetricLowerFactor(
      normalizedX: x,
      isRightSide: false,
    );
    final lowerRight = ProceduralVoiceWaveform.asymmetricLowerFactor(
      normalizedX: x,
      isRightSide: true,
    );
    expect(lowerLeft.isFinite, isTrue);
    expect(lowerRight.isFinite, isTrue);
    expect(lowerLeft, isNot(closeTo(lowerRight, 0.000001)));
  });

  test('radial bar energy is state-independent and finite', () {
    const angle = 1.2;
    const time = 0.55;

    final sample = ProceduralVoiceWaveform.radialBarEnergy(
      angle: angle,
      time: time,
    );
    expect(sample.isFinite, isTrue);
    expect(sample, inInclusiveRange(0.0, 1.0));

    for (final state in Gate3InteractionState.values) {
      expect(
        ProceduralVoiceWaveform.radialBarEnergy(angle: angle, time: time),
        sample,
        reason: 'state=$state must not affect circular energy',
      );
    }
  });

  test('phase derivation keeps circular speed constant and horizontal state-responsive',
      () {
    const controllerValue = 0.37;

    final idlePhases = SediAudioVisualizerPainter.derivePhases(
      controllerValue: controllerValue,
      state: Gate3InteractionState.idle,
    );
    final speakingPhases = SediAudioVisualizerPainter.derivePhases(
      controllerValue: controllerValue,
      state: Gate3InteractionState.speaking,
    );

    expect(idlePhases.circular, closeTo(controllerValue * 0.85, 0.0001));
    expect(
      speakingPhases.circular,
      closeTo(controllerValue * 0.85, 0.0001),
    );
    expect(
      speakingPhases.horizontal,
      greaterThan(idlePhases.horizontal),
    );
    expect(
      SediAudioVisualizerPainter.circularPhaseSpeed(
        Gate3InteractionState.thinking,
      ),
      SediAudioVisualizerPainter.circularPhaseSpeed(
        Gate3InteractionState.speaking,
      ),
    );
    expect(
      SediAudioVisualizerPainter.horizontalPhaseSpeed(
        Gate3InteractionState.speaking,
      ),
      greaterThan(
        SediAudioVisualizerPainter.horizontalPhaseSpeed(
          Gate3InteractionState.thinking,
        ),
      ),
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
      final layout = SediAudioVisualizerPainter.resolveLayout(
        width: width,
        containerHeight: canvasHeight,
        orbBodyRadius: SediBrainOrb.orbBodyRadius,
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
          amplitude: SediCircularEqualizerProfile.amplitude,
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
    );

    expect(layout.spectrumRadius.isFinite, isTrue);
    expect(layout.spectrumRadius, greaterThan(0));
    expect(layout.barExtensionFactor, inInclusiveRange(0.0, 1.0));
    expect(layout.glowPaintRadiusBeyondSpectrum, inInclusiveRange(0.0, 6.0));
    expect(layout.glowShaderExtraBeyondBarExtension, inInclusiveRange(0.0, 4.0));

    expect(
      SediAudioVisualizerGeometry.paintedExtentFits(
        width: width,
        containerHeight: canvasHeight,
        layout: layout,
        amplitude: SediCircularEqualizerProfile.amplitude,
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

    expect(resolved.isFinite, isTrue);
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

  testWidgets('SediBrainOrb renders wordmark at 80% ratio inside orb',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SediBrainOrb(
            state: Gate3InteractionState.idle,
            canvasHeight: SediBrainOrb.preferredVisualizerCanvasHeight,
          ),
        ),
      ),
    );

    await tester.pump(const Duration(milliseconds: 32));

    final lockup = tester.widget<SediBrandLockup>(find.byType(SediBrandLockup));
    final expectedHeight =
        SediBrainOrb.orbDiameter * SediBrainOrb.brandHeightRatio;
    expect(lockup.height, closeTo(expectedHeight, 0.0001));
    expect(lockup.height, closeTo(SediBrainOrb.orbDiameter * 0.272, 0.0001));
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
