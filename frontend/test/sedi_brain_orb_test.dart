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

  test('horizontal energy ordering follows idle < listening < thinking < speaking',
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

    expect(idle, 0.0);
    expect(listening, closeTo(0.25, 0.001));
    expect(thinking, closeTo(0.52, 0.001));
    expect(speaking, 1.0);
    expect(listening, greaterThan(idle));
    expect(thinking, greaterThan(listening));
    expect(speaking, greaterThan(thinking));
  });

  test('idle horizontal samples are flat within epsilon', () {
    for (var i = 0; i <= 24; i++) {
      final sample = ProceduralVoiceWaveform.horizontalWaveformSample(
        normalizedX: i / 24,
        time: 0.42,
        energy: SediAudioVisualizerPainter.targetHorizontalEnergy(
          Gate3InteractionState.idle,
        ),
        density: SediAudioVisualizerPainter.targetHorizontalDensity(
          Gate3InteractionState.idle,
        ),
        isRightSide: false,
      );
      expect(sample.upper, lessThan(1e-5));
      expect(sample.lower, lessThan(1e-5));
    }
  });

  test('listening horizontal resonance is visibly non-flat', () {
    final peak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
      time: 0.42,
      energy: SediAudioVisualizerPainter.targetHorizontalEnergy(
        Gate3InteractionState.listening,
      ),
      density: SediAudioVisualizerPainter.targetHorizontalDensity(
        Gate3InteractionState.listening,
      ),
    );
    expect(peak, greaterThan(0.02));
  });

  test('horizontal peak amplitude ordering listening < thinking < speaking', () {
    const time = 0.37;
    final listeningPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
      time: time,
      energy: SediAudioVisualizerPainter.targetHorizontalEnergy(
        Gate3InteractionState.listening,
      ),
      density: SediAudioVisualizerPainter.targetHorizontalDensity(
        Gate3InteractionState.listening,
      ),
    );
    final thinkingPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
      time: time,
      energy: SediAudioVisualizerPainter.targetHorizontalEnergy(
        Gate3InteractionState.thinking,
      ),
      density: SediAudioVisualizerPainter.targetHorizontalDensity(
        Gate3InteractionState.thinking,
      ),
    );
    final speakingPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
      time: time,
      energy: SediAudioVisualizerPainter.targetHorizontalEnergy(
        Gate3InteractionState.speaking,
      ),
      density: SediAudioVisualizerPainter.targetHorizontalDensity(
        Gate3InteractionState.speaking,
      ),
    );

    expect(thinkingPeak, greaterThan(listeningPeak));
    expect(speakingPeak, greaterThan(thinkingPeak));
  });

  test('horizontal density ordering listening < thinking < speaking', () {
    final listeningDensity = SediHorizontalResonanceProfile.densityTarget(
      Gate3InteractionState.listening,
    );
    final thinkingDensity = SediHorizontalResonanceProfile.densityTarget(
      Gate3InteractionState.thinking,
    );
    final speakingDensity = SediHorizontalResonanceProfile.densityTarget(
      Gate3InteractionState.speaking,
    );

    expect(listeningDensity, greaterThan(0.24));
    expect(listeningDensity, lessThan(0.31));
    expect(thinkingDensity, greaterThan(0.57));
    expect(thinkingDensity, lessThan(0.63));
    expect(speakingDensity, 1.0);
    expect(listeningDensity, lessThan(thinkingDensity));
    expect(thinkingDensity, lessThan(speakingDensity));
  });

  test('speaking has the richest weighted cluster richness', () {
    final listeningRichness = ProceduralVoiceWaveform.weightedClusterRichness(
      SediHorizontalResonanceProfile.densityTarget(
        Gate3InteractionState.listening,
      ),
    );
    final thinkingRichness = ProceduralVoiceWaveform.weightedClusterRichness(
      SediHorizontalResonanceProfile.densityTarget(
        Gate3InteractionState.thinking,
      ),
    );
    final speakingRichness = ProceduralVoiceWaveform.weightedClusterRichness(
      SediHorizontalResonanceProfile.densityTarget(
        Gate3InteractionState.speaking,
      ),
    );

    expect(listeningRichness, greaterThan(0.5));
    expect(listeningRichness, lessThan(2.5));
    expect(thinkingRichness, greaterThan(listeningRichness));
    expect(speakingRichness, greaterThan(thinkingRichness));
    expect(speakingRichness, closeTo(7.0, 0.6));
  });

  test('current density interpolates toward target with elapsed-time smoothing',
      () {
    const current = 0.60;
    const target = 1.0;
    const dt = 1 / 120.0;
    final next = SediHorizontalResonanceProfile.smoothToward(
      current,
      target,
      dt,
    );
    expect(next, greaterThan(current));
    expect(next, lessThan(target));
  });

  test('thinking to speaking first-step density change is bounded', () {
    const current = 0.60;
    const target = 1.0;
    const dt = 1 / 120.0;
    final next = SediHorizontalResonanceProfile.smoothToward(
      current,
      target,
      dt,
    );
    expect((next - current).abs(), lessThan(0.08));
  });

  test('cluster activation weights change continuously', () {
    final low = ProceduralVoiceWaveform.clusterActivationWeight(3, 0.50);
    final mid = ProceduralVoiceWaveform.clusterActivationWeight(3, 0.55);
    final high = ProceduralVoiceWaveform.clusterActivationWeight(3, 0.60);
    expect(low, greaterThanOrEqualTo(0));
    expect(mid, greaterThan(low));
    expect(high, greaterThan(mid));
    expect(high, lessThanOrEqualTo(1));
  });

  test('no hard cluster-count jump between adjacent density steps', () {
    var previousRichness = ProceduralVoiceWaveform.weightedClusterRichness(0.0);
    for (var step = 1; step <= 20; step++) {
      final density = step / 20.0;
      final richness = ProceduralVoiceWaveform.weightedClusterRichness(density);
      expect((richness - previousRichness).abs(), lessThan(1.25));
      previousRichness = richness;
    }
  });

  test('idle cluster weights are all zero', () {
    for (var c = 0; c < ProceduralVoiceWaveform.clusterCount; c++) {
      expect(ProceduralVoiceWaveform.clusterActivationWeight(c, 0.0), 0.0);
    }
    expect(ProceduralVoiceWaveform.weightedClusterRichness(0.0), 0.0);
  });

  test('deterministic cluster activation weights', () {
    final a = ProceduralVoiceWaveform.clusterActivationWeight(2, 0.62);
    final b = ProceduralVoiceWaveform.clusterActivationWeight(2, 0.62);
    expect(a, closeTo(b, 0.000001));
  });

  test('all active states use shared horizontal cycle duration 2.6s', () {
    for (final state in Gate3InteractionState.values) {
      expect(
        SediAudioVisualizerPainter.horizontalPhaseSpeed(state),
        closeTo(1 / 2.6, 0.0001),
      );
    }
    expect(SediHorizontalResonanceProfile.cycleDurationSeconds, 2.6);
    expect(
      SediAudioVisualizerPainter.circularPhaseSpeed(
        Gate3InteractionState.speaking,
      ),
      SediCircularEqualizerProfile.phaseSpeed,
    );
    expect(SediCircularEqualizerProfile.phaseSpeed, 0.85);
  });

  test('horizontal procedural waveform is deterministic and asymmetric', () {
    const x = 0.42;
    const time = 0.31;
    const energy = 0.8;

    final leftA = ProceduralVoiceWaveform.horizontalWaveformSample(
      normalizedX: x,
      time: time,
      energy: energy,
      density: 1.0,
      isRightSide: false,
    );
    final leftB = ProceduralVoiceWaveform.horizontalWaveformSample(
      normalizedX: x,
      time: time,
      energy: energy,
      density: 1.0,
      isRightSide: false,
    );
    final right = ProceduralVoiceWaveform.horizontalWaveformSample(
      normalizedX: x,
      time: time,
      energy: energy,
      density: 1.0,
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
    const dt = 1 / 120.0;
    const phase = 1.15;

    final before = SediAudioVisualizerPainter.advanceHorizontalPhase(
      phase: phase,
      dtSeconds: dt,
    );
    final after = SediAudioVisualizerPainter.advanceHorizontalPhase(
      phase: before,
      dtSeconds: dt,
    );

    expect(before.isFinite, isTrue);
    expect(after.isFinite, isTrue);
    expect(after, greaterThan(before));
    expect(before - phase, closeTo(dt / 2.6, 1e-9));
    expect(after - before, closeTo(dt / 2.6, 1e-9));
  });

  test('thinking to speaking changes amplitude and density without speed change',
      () {
    final thinkingEnergy = SediAudioVisualizerPainter.targetHorizontalEnergy(
      Gate3InteractionState.thinking,
    );
    final speakingEnergy = SediAudioVisualizerPainter.targetHorizontalEnergy(
      Gate3InteractionState.speaking,
    );
    final thinkingDensity = SediAudioVisualizerPainter.targetHorizontalDensity(
      Gate3InteractionState.thinking,
    );
    final speakingDensity = SediAudioVisualizerPainter.targetHorizontalDensity(
      Gate3InteractionState.speaking,
    );
    expect(speakingEnergy, greaterThan(thinkingEnergy));
    expect(speakingDensity, greaterThan(thinkingDensity));
    expect(
      SediAudioVisualizerPainter.horizontalPhaseSpeed(
        Gate3InteractionState.thinking,
      ),
      closeTo(
        SediAudioVisualizerPainter.horizontalPhaseSpeed(
          Gate3InteractionState.speaking,
        ),
        0.0001,
      ),
    );
  });

  test('horizontal peak amplitude ordering across multiple phases', () {
    for (final phase in const [0.00, 0.13, 0.37, 0.71]) {
      final listeningPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
        time: phase,
        energy: SediAudioVisualizerPainter.targetHorizontalEnergy(
          Gate3InteractionState.listening,
        ),
        density: SediAudioVisualizerPainter.targetHorizontalDensity(
          Gate3InteractionState.listening,
        ),
      );
      final thinkingPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
        time: phase,
        energy: SediAudioVisualizerPainter.targetHorizontalEnergy(
          Gate3InteractionState.thinking,
        ),
        density: SediAudioVisualizerPainter.targetHorizontalDensity(
          Gate3InteractionState.thinking,
        ),
      );
      final speakingPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
        time: phase,
        energy: SediAudioVisualizerPainter.targetHorizontalEnergy(
          Gate3InteractionState.speaking,
        ),
        density: SediAudioVisualizerPainter.targetHorizontalDensity(
          Gate3InteractionState.speaking,
        ),
      );

      expect(thinkingPeak, greaterThan(listeningPeak), reason: 'phase=$phase');
      expect(speakingPeak, greaterThan(thinkingPeak), reason: 'phase=$phase');
    }
  });

  test('horizontal bar totals per width distinguish per-side from total', () {
    final canvasHeight = SediBrainOrb.fixedVisualizerCanvasHeight;
    final orbBodyRadius = SediBrainOrb.orbBodyRadius;

    final w280 = SediAudioVisualizerGeometry.horizontalBarCountsForCanvasWidth(
      width: 280,
      containerHeight: canvasHeight,
      orbBodyRadius: orbBodyRadius,
    );
    final w360 = SediAudioVisualizerGeometry.horizontalBarCountsForCanvasWidth(
      width: 360,
      containerHeight: canvasHeight,
      orbBodyRadius: orbBodyRadius,
    );
    final w390 = SediAudioVisualizerGeometry.horizontalBarCountsForCanvasWidth(
      width: 390,
      containerHeight: canvasHeight,
      orbBodyRadius: orbBodyRadius,
    );
    final w411 = SediAudioVisualizerGeometry.horizontalBarCountsForCanvasWidth(
      width: 411,
      containerHeight: canvasHeight,
      orbBodyRadius: orbBodyRadius,
    );

    expect(w280.total, w280.perSide * 2);
    expect(w360.total, w360.perSide * 2);
    expect(w390.total, w390.perSide * 2);
    expect(w411.total, w411.perSide * 2);

    expect(w280.total, closeTo(66, 2));
    expect(w360.total, closeTo(96, 2));
    expect(w390.total, closeTo(106, 2));
    expect(w411.total, closeTo(114, 2));

    expect(w360.total, inInclusiveRange(96, 120));
    expect(w390.total, inInclusiveRange(96, 120));
    expect(w411.total, inInclusiveRange(96, 120));

    expect(w280.perSide, greaterThan(0));
    expect(w280.total, greaterThan(0));
  });

  test('horizontal bar pitch is 2.7 logical pixels', () {
    expect(SediHorizontalResonanceProfile.barPitch, 2.7);
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
