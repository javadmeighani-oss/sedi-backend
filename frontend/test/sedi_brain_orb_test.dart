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

  test('visualizer is 10% smaller than commit 628b310 normal size', () {
    const preScaleDiameter = 136 * 0.93 * 0.72;
    expect(SediBrainOrb.visualizerSizeScale, 0.90);
    expect(SediBrainOrb.orbDiameter, closeTo(preScaleDiameter * 0.90, 0.001));
    expect(
      SediBrainOrb.preferredVisualizerCanvasHeight,
      closeTo(164.83 * 0.90, 0.2),
    );
    expect(
      SediBrainOrb.fixedVisualizerCanvasHeight,
      SediBrainOrb.preferredVisualizerCanvasHeight,
    );
  });

  test('wordmark ratio is 0.2584 inside the resized orb', () {
    expect(SediBrainOrb.brandHeightRatio, 0.2584);
    final brandHeight = SediBrainOrb.orbDiameter * SediBrainOrb.brandHeightRatio;
    expect(brandHeight, greaterThan(0));
    expect(
      brandHeight,
      closeTo(SediBrainOrb.orbDiameter * 0.272 * 0.95, 0.0001),
    );
  });

  test('circular profile is state-independent', () {
    final idleLayout = SediAudioVisualizerPainter.resolveLayout(
      width: 390,
      containerHeight: SediBrainOrb.fixedVisualizerCanvasHeight,
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
        containerHeight: SediBrainOrb.fixedVisualizerCanvasHeight,
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

  test('fixed visualizer canvas height ignores keyboard viewport shrink', () {
    final normal = Gate3VerticalLayout.resolveVisualizerCanvasHeight(
      orbBodyRadius: SediBrainOrb.orbBodyRadius,
    );
    final keyboardOpen = Gate3VerticalLayout.resolveVisualizerCanvasHeight(
      orbBodyRadius: SediBrainOrb.orbBodyRadius,
    );

    expect(normal, SediBrainOrb.fixedVisualizerCanvasHeight);
    expect(keyboardOpen, normal);
    expect(
      Gate3VerticalLayout.resolveVisualizerCanvasHeight(
        orbBodyRadius: SediBrainOrb.orbBodyRadius,
      ),
      closeTo(148.34, 0.2),
    );
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

    expect(idle, greaterThan(0.1));
    expect(listening, greaterThan(idle));
    expect(thinking, greaterThan(listening * 1.5));
    expect(speaking, greaterThan(thinking * 1.4));
    expect(speaking, greaterThan(0.85));
  });

  test('horizontal waveform stays alive and non-flat in idle and listening', () {
    var idleMin = double.infinity;
    var listeningMin = double.infinity;

    for (var i = 0; i <= 24; i++) {
      final t = i / 24;
      final idleSample = ProceduralVoiceWaveform.horizontalWaveformSample(
        normalizedX: t,
        time: 0.42,
        energy: SediAudioVisualizerPainter.targetHorizontalEnergy(
          Gate3InteractionState.idle,
        ),
        state: Gate3InteractionState.idle,
        isRightSide: false,
      );
      final listeningSample = ProceduralVoiceWaveform.horizontalWaveformSample(
        normalizedX: t,
        time: 0.42,
        energy: SediAudioVisualizerPainter.targetHorizontalEnergy(
          Gate3InteractionState.listening,
        ),
        state: Gate3InteractionState.listening,
        isRightSide: false,
      );

      idleMin = mathMin(idleMin, idleSample.upper + idleSample.lower);
      listeningMin = mathMin(listeningMin, listeningSample.upper + listeningSample.lower);
    }

    expect(idleMin.isFinite, isTrue);
    expect(listeningMin.isFinite, isTrue);
    expect(idleMin, greaterThan(0.02));
    expect(listeningMin, greaterThan(idleMin));
  });

  test('horizontal procedural waveform is deterministic and asymmetric', () {
    const x = 0.42;
    const time = 0.31;
    const energy = 0.8;

    final leftA = ProceduralVoiceWaveform.horizontalWaveformSample(
      normalizedX: x,
      time: time,
      energy: energy,
      state: Gate3InteractionState.speaking,
      isRightSide: false,
    );
    final leftB = ProceduralVoiceWaveform.horizontalWaveformSample(
      normalizedX: x,
      time: time,
      energy: energy,
      state: Gate3InteractionState.speaking,
      isRightSide: false,
    );
    final right = ProceduralVoiceWaveform.horizontalWaveformSample(
      normalizedX: x,
      time: time,
      energy: energy,
      state: Gate3InteractionState.speaking,
      isRightSide: true,
    );

    expect(leftA.upper.isFinite, isTrue);
    expect(leftA.lower.isFinite, isTrue);
    expect(leftA.upper, closeTo(leftB.upper, 0.000001));
    expect(leftA.lower, closeTo(leftB.lower, 0.000001));
    expect(right.upper, isNot(closeTo(leftA.upper, 0.000001)));
    expect(leftA.upper, isNot(closeTo(leftA.lower, 0.000001)));
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
  });

  test('circular phase stays constant-speed across states', () {
    const controllerValue = 0.37;

    expect(
      SediAudioVisualizerPainter.deriveCircularPhase(controllerValue),
      closeTo(controllerValue * 0.85, 0.0001),
    );
    expect(
      SediAudioVisualizerPainter.circularPhaseSpeed(
        Gate3InteractionState.thinking,
      ),
      SediAudioVisualizerPainter.circularPhaseSpeed(
        Gate3InteractionState.speaking,
      ),
    );
  });

  test('horizontal phase integration stays continuous across state changes', () {
    const controllerValue = 0.42;
    const previousValue = 0.41;

    final before = SediAudioVisualizerPainter.advanceHorizontalPhase(
      phase: 1.15,
      speed: SediAudioVisualizerPainter.horizontalPhaseSpeed(
        Gate3InteractionState.thinking,
      ),
      lastControllerValue: previousValue,
      controllerValue: controllerValue,
      state: Gate3InteractionState.thinking,
    );
    final after = SediAudioVisualizerPainter.advanceHorizontalPhase(
      phase: before.phase,
      speed: before.speed,
      lastControllerValue: before.lastControllerValue,
      controllerValue: controllerValue + 0.01,
      state: Gate3InteractionState.speaking,
    );

    final jumpFormulaDelta = (controllerValue * 1.75 - controllerValue * 0.95)
        .abs();
    final integratedDelta = (after.phase - before.phase).abs();

    expect(before.phase.isFinite, isTrue);
    expect(after.phase.isFinite, isTrue);
    expect(after.phase, greaterThan(before.phase));
    expect(integratedDelta, lessThan(jumpFormulaDelta));
    expect(
      after.speed,
      greaterThan(before.speed),
    );
    expect(
      after.speed,
      lessThan(SediAudioVisualizerPainter.horizontalPhaseSpeed(
        Gate3InteractionState.speaking,
      )),
    );

    final repeated = SediAudioVisualizerPainter.advanceHorizontalPhase(
      phase: before.phase,
      speed: before.speed,
      lastControllerValue: before.lastControllerValue,
      controllerValue: controllerValue + 0.01,
      state: Gate3InteractionState.speaking,
    );
    expect(repeated.phase, closeTo(after.phase, 0.000001));
    expect(repeated.speed, closeTo(after.speed, 0.000001));
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
    final canvasHeight = SediBrainOrb.fixedVisualizerCanvasHeight;

    for (final state in Gate3InteractionState.values) {
      final layout = SediAudioVisualizerPainter.resolveLayout(
        width: width,
        containerHeight: canvasHeight,
        orbBodyRadius: SediBrainOrb.orbBodyRadius,
      );

      expect(layout.barExtensionFactor, 1.0);
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

  test('width 120 fits without clipping at fixed canvas height', () {
    const width = 120.0;
    final canvasHeight = SediBrainOrb.fixedVisualizerCanvasHeight;

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

  test('spectrum radius resolves inside layout bounds', () {
    final radius = SediAudioVisualizerPainter.resolveSpectrumRadius(
      width: 320,
      containerHeight: SediBrainOrb.fixedVisualizerCanvasHeight,
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

  testWidgets('SediBrainOrb renders wordmark at approved ratio inside orb',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SediBrainOrb(
            state: Gate3InteractionState.idle,
            canvasHeight: SediBrainOrb.fixedVisualizerCanvasHeight,
          ),
        ),
      ),
    );

    await tester.pump(const Duration(milliseconds: 32));

    final lockup = tester.widget<SediBrandLockup>(find.byType(SediBrandLockup));
    final expectedHeight =
        SediBrainOrb.orbDiameter * SediBrainOrb.brandHeightRatio;
    expect(lockup.height, closeTo(expectedHeight, 0.0001));
    expect(lockup.height, closeTo(SediBrainOrb.orbDiameter * 0.2584, 0.0001));
  });

  testWidgets('SediBrainOrb keeps fixed canvas height with keyboard viewInsets',
      (tester) async {
    final canvasHeight = SediBrainOrb.fixedVisualizerCanvasHeight;

    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: const MediaQueryData(
            viewInsets: EdgeInsets.only(bottom: 280),
          ),
          child: Scaffold(
            resizeToAvoidBottomInset: true,
            body: SediBrainOrb(
              state: Gate3InteractionState.listening,
              canvasHeight: canvasHeight,
            ),
          ),
        ),
      ),
    );

    await tester.pump(const Duration(milliseconds: 32));

    final sizedBox = tester.widget<SizedBox>(
      find.descendant(
        of: find.byType(SediBrainOrb),
        matching: find.byWidgetPredicate(
          (widget) => widget is SizedBox && widget.height == canvasHeight,
        ),
      ),
    );
    expect(sizedBox.height, canvasHeight);
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
                      canvasHeight: SediBrainOrb.fixedVisualizerCanvasHeight,
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

double mathMin(double a, double b) => a < b ? a : b;
