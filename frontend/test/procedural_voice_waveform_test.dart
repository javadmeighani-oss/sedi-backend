import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/features/gate3_interactive/logic/procedural_voice_waveform.dart';
import 'package:sedi_app/features/gate3_interactive/models/gate3_interaction_state.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_audio_visualizer_geometry.dart';
import 'package:sedi_app/features/gate3_interactive/presentation/widgets/sedi_audio_visualizer_painter.dart';

const _samplePhases = [0.00, 0.13, 0.37, 0.71];

void main() {
  const time = 0.37;
  double energy(Gate3InteractionState state) =>
      SediAudioVisualizerPainter.targetHorizontalEnergy(state);

  double density(Gate3InteractionState state) =>
      SediAudioVisualizerPainter.targetHorizontalDensity(state);

  test('idle has zero vertical bar resonance', () {
    for (var i = 0; i <= 32; i++) {
      final sample = ProceduralVoiceWaveform.horizontalWaveformSample(
        normalizedX: i / 32,
        time: time,
        energy: energy(Gate3InteractionState.idle),
        density: density(Gate3InteractionState.idle),
        isRightSide: false,
      );
      expect(sample.upper, lessThan(1e-5));
      expect(sample.lower, lessThan(1e-5));
    }
    expect(
      ProceduralVoiceWaveform.horizontalPeakAmplitude(
        time: time,
        energy: energy(Gate3InteractionState.idle),
        density: density(Gate3InteractionState.idle),
      ),
      lessThan(1e-5),
    );
  });

  test('listening has short nonzero bars', () {
    final peak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
      time: time,
      energy: energy(Gate3InteractionState.listening),
      density: density(Gate3InteractionState.listening),
    );
    expect(peak, greaterThan(0.02));
    expect(peak, lessThan(0.55));
  });

  test('thinking amplitude exceeds listening', () {
    for (final time in _samplePhases) {
      final listeningPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
        time: time,
        energy: energy(Gate3InteractionState.listening),
        density: density(Gate3InteractionState.listening),
      );
      final thinkingPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
        time: time,
        energy: energy(Gate3InteractionState.thinking),
        density: density(Gate3InteractionState.thinking),
      );
      expect(
        thinkingPeak,
        greaterThan(listeningPeak),
        reason: 'phase=$time',
      );
    }
  });

  test('speaking amplitude exceeds thinking', () {
    for (final time in _samplePhases) {
      final thinkingPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
        time: time,
        energy: energy(Gate3InteractionState.thinking),
        density: density(Gate3InteractionState.thinking),
      );
      final speakingPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
        time: time,
        energy: energy(Gate3InteractionState.speaking),
        density: density(Gate3InteractionState.speaking),
      );
      expect(
        speakingPeak,
        greaterThan(thinkingPeak),
        reason: 'phase=$time',
      );
    }
  });

  test('density ordering is idle < listening < thinking < speaking', () {
    final idle = density(Gate3InteractionState.idle);
    final listening = density(Gate3InteractionState.listening);
    final thinking = density(Gate3InteractionState.thinking);
    final speaking = density(Gate3InteractionState.speaking);

    expect(idle, 0.0);
    expect(listening, closeTo(0.28, 0.001));
    expect(thinking, closeTo(0.60, 0.001));
    expect(speaking, 1.0);
    expect(listening, greaterThan(idle));
    expect(thinking, greaterThan(listening));
    expect(speaking, greaterThan(thinking));
  });

  test('mean and peak height ordering listening < thinking < speaking', () {
    for (final phase in _samplePhases) {
      final listeningMean = ProceduralVoiceWaveform.horizontalMeanAmplitude(
        time: phase,
        energy: energy(Gate3InteractionState.listening),
        density: density(Gate3InteractionState.listening),
      );
      final thinkingMean = ProceduralVoiceWaveform.horizontalMeanAmplitude(
        time: phase,
        energy: energy(Gate3InteractionState.thinking),
        density: density(Gate3InteractionState.thinking),
      );
      final speakingMean = ProceduralVoiceWaveform.horizontalMeanAmplitude(
        time: phase,
        energy: energy(Gate3InteractionState.speaking),
        density: density(Gate3InteractionState.speaking),
      );

      final listeningPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
        time: phase,
        energy: energy(Gate3InteractionState.listening),
        density: density(Gate3InteractionState.listening),
      );
      final thinkingPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
        time: phase,
        energy: energy(Gate3InteractionState.thinking),
        density: density(Gate3InteractionState.thinking),
      );
      final speakingPeak = ProceduralVoiceWaveform.horizontalPeakAmplitude(
        time: phase,
        energy: energy(Gate3InteractionState.speaking),
        density: density(Gate3InteractionState.speaking),
      );

      expect(thinkingMean, greaterThan(listeningMean), reason: 'mean phase=$phase');
      expect(speakingMean, greaterThan(thinkingMean), reason: 'mean phase=$phase');
      expect(thinkingPeak, greaterThan(listeningPeak), reason: 'peak phase=$phase');
      expect(speakingPeak, greaterThan(thinkingPeak), reason: 'peak phase=$phase');
    }
  });
  test('generated values are finite and clamped', () {
    for (var i = 0; i <= 24; i++) {
      final sample = ProceduralVoiceWaveform.horizontalWaveformSample(
        normalizedX: i / 24,
        time: time,
        energy: 1.0,
        density: 1.0,
        isRightSide: i.isEven,
      );
      expect(sample.upper.isFinite, isTrue);
      expect(sample.lower.isFinite, isTrue);
      expect(sample.upper, inInclusiveRange(0.0, 1.0));
      expect(sample.lower, inInclusiveRange(0.0, 1.0));
    }
  });

  test('identical inputs produce identical output', () {
    const x = 0.42;
    final a = ProceduralVoiceWaveform.horizontalWaveformSample(
      normalizedX: x,
      time: time,
      energy: 0.8,
      density: 0.9,
      isRightSide: false,
    );
    final b = ProceduralVoiceWaveform.horizontalWaveformSample(
      normalizedX: x,
      time: time,
      energy: 0.8,
      density: 0.9,
      isRightSide: false,
    );
    expect(a.upper, closeTo(b.upper, 1e-9));
    expect(a.lower, closeTo(b.lower, 1e-9));
  });

  test('upper lower and left right output is not exactly mirrored', () {
    const x = 0.42;
    final left = ProceduralVoiceWaveform.horizontalWaveformSample(
      normalizedX: x,
      time: time,
      energy: 0.9,
      density: 1.0,
      isRightSide: false,
    );
    final right = ProceduralVoiceWaveform.horizontalWaveformSample(
      normalizedX: x,
      time: time,
      energy: 0.9,
      density: 1.0,
      isRightSide: true,
    );
    expect(left.upper, isNot(closeTo(right.upper, 0.000001)));
    expect(left.lower, isNot(closeTo(right.lower, 0.000001)));
    expect(left.upper, isNot(closeTo(left.lower, 0.000001)));
  });

  test('phase remains continuous across state changes', () {
    const phase = 1.15;
    const dt = 1 / 120.0;
    final first = SediAudioVisualizerPainter.advanceHorizontalPhase(
      phase: phase,
      dtSeconds: dt,
    );
    final second = SediAudioVisualizerPainter.advanceHorizontalPhase(
      phase: first,
      dtSeconds: dt,
    );
    expect(second, greaterThan(first));
    expect(first - phase, closeTo(dt / 2.6, 1e-9));
    expect(second - first, closeTo(dt / 2.6, 1e-9));
  });

  test('density interpolation does not pop clusters', () {
    var previous = ProceduralVoiceWaveform.weightedClusterRichness(0.0);
    for (var step = 1; step <= 24; step++) {
      final d = step / 24.0;
      final richness = ProceduralVoiceWaveform.weightedClusterRichness(d);
      expect((richness - previous).abs(), lessThan(1.1));
      previous = richness;
    }
  });

  test('equivalent elapsed time at 60Hz and 120Hz produces equivalent smoothing',
      () {
    const current = 0.25;
    const target = 1.0;
    const tau = SediHorizontalResonanceProfile.transitionTauSeconds;

    var value60 = current;
    for (var i = 0; i < 60; i++) {
      value60 = SediHorizontalResonanceProfile.smoothToward(
        value60,
        target,
        1 / 60.0,
        tauSeconds: tau,
      );
    }

    var value120 = current;
    for (var i = 0; i < 120; i++) {
      value120 = SediHorizontalResonanceProfile.smoothToward(
        value120,
        target,
        1 / 120.0,
        tauSeconds: tau,
      );
    }

    expect(value60, closeTo(value120, 0.02));
    expect(value120, greaterThan(current));
    expect(value120, lessThan(target));
  });

  test('listening thinking speaking use the same temporal speed', () {
    const dt = 0.016;
  const phase = 0.5;
    final speed = SediAudioVisualizerPainter.horizontalPhaseSpeed(
      Gate3InteractionState.listening,
    );
    expect(
      SediAudioVisualizerPainter.horizontalPhaseSpeed(
        Gate3InteractionState.thinking,
      ),
      speed,
    );
    expect(
      SediAudioVisualizerPainter.horizontalPhaseSpeed(
        Gate3InteractionState.speaking,
      ),
      speed,
    );
    expect(speed, closeTo(1 / 2.6, 0.0001));

    final advanced = SediAudioVisualizerPainter.advanceHorizontalPhase(
      phase: phase,
      dtSeconds: dt,
    );
    expect(advanced - phase, closeTo(dt / 2.6, 1e-9));
  });

  test('cluster activation weights change continuously', () {
    final low = ProceduralVoiceWaveform.clusterActivationWeight(3, 0.50);
    final mid = ProceduralVoiceWaveform.clusterActivationWeight(3, 0.55);
    final high = ProceduralVoiceWaveform.clusterActivationWeight(3, 0.60);
    expect(mid, greaterThan(low));
    expect(high, greaterThan(mid));
    expect(high, lessThanOrEqualTo(1.0));
  });

  test('speaking has the richest weighted cluster richness', () {
    final listeningRichness = ProceduralVoiceWaveform.weightedClusterRichness(
      density(Gate3InteractionState.listening),
    );
    final thinkingRichness = ProceduralVoiceWaveform.weightedClusterRichness(
      density(Gate3InteractionState.thinking),
    );
    final speakingRichness = ProceduralVoiceWaveform.weightedClusterRichness(
      density(Gate3InteractionState.speaking),
    );

    expect(thinkingRichness, greaterThan(listeningRichness));
    expect(speakingRichness, greaterThan(thinkingRichness));
    expect(speakingRichness, closeTo(7.0, 0.8));
  });

  test('long resume delta produces safeDt = 0', () {
    const last = 1.0;
    const elapsed = last + 0.5;
    final sanitized = SediHorizontalResonanceProfile.sanitizeVisualDelta(
      elapsedSeconds: elapsed,
      lastElapsedSeconds: last,
    );
    expect(sanitized.safeDt, 0.0);
    expect(sanitized.lastElapsedSeconds, elapsed);
  });

  test('next normal frame after resume gap is accepted normally', () {
    const last = 1.0;
    const resumeElapsed = last + 0.5;
    final resume = SediHorizontalResonanceProfile.sanitizeVisualDelta(
      elapsedSeconds: resumeElapsed,
      lastElapsedSeconds: last,
    );
    expect(resume.safeDt, 0.0);

    final next = SediHorizontalResonanceProfile.sanitizeVisualDelta(
      elapsedSeconds: resumeElapsed + 1 / 120.0,
      lastElapsedSeconds: resume.lastElapsedSeconds,
    );
    expect(next.safeDt, closeTo(1 / 120.0, 1e-9));
  });

  test('moderate frame delay is capped to 1/30s', () {
    const last = 2.0;
    const elapsed = last + 0.05;
    final sanitized = SediHorizontalResonanceProfile.sanitizeVisualDelta(
      elapsedSeconds: elapsed,
      lastElapsedSeconds: last,
    );
    expect(
      sanitized.safeDt,
      closeTo(SediHorizontalResonanceProfile.maxVisualDeltaSeconds, 1e-9),
    );
  });

  test('60Hz and 120Hz deltas pass through sanitizer unchanged', () {
    for (final dt in [1 / 60.0, 1 / 120.0]) {
      final sanitized = SediHorizontalResonanceProfile.sanitizeVisualDelta(
        elapsedSeconds: 1.0 + dt,
        lastElapsedSeconds: 1.0,
      );
      expect(sanitized.safeDt, closeTo(dt, 1e-9));
    }
  });

  test('sanitized delta drives phase energy and density consistently', () {
    const phase = 0.4;
    const energy = 0.25;
    const density = 0.28;
    const dt = 1 / 120.0;

    final advanced = SediHorizontalResonanceProfile.advanceVisualState(
      phase: phase,
      energy: energy,
      density: density,
      elapsedSeconds: 1.0 + dt,
      lastElapsedSeconds: 1.0,
      energyTarget: 1.0,
      densityTarget: 1.0,
    );

    expect(advanced.safeDt, closeTo(dt, 1e-9));
    expect(
      advanced.phase,
      closeTo(phase + dt / SediHorizontalResonanceProfile.cycleDurationSeconds, 1e-9),
    );
    expect(
      advanced.energy,
      closeTo(
        SediHorizontalResonanceProfile.smoothToward(energy, 1.0, dt),
        1e-9,
      ),
    );
    expect(
      advanced.density,
      closeTo(
        SediHorizontalResonanceProfile.smoothToward(density, 1.0, dt),
        1e-9,
      ),
    );
  });

  test('maximum bar endpoints remain within canvas budget', () {
    final budget = SediAudioVisualizerGeometry.horizontalBarHalfHeightBudget();
    final speakingPeak = SediAudioVisualizerGeometry.clampHorizontalPeakHeight(
      3.0 + SediHorizontalResonanceProfile.amplitudeTarget(
            Gate3InteractionState.speaking,
          ) *
          16,
    );
    final thinkingPeak = SediAudioVisualizerGeometry.clampHorizontalPeakHeight(
      3.0 + SediHorizontalResonanceProfile.amplitudeTarget(
            Gate3InteractionState.thinking,
          ) *
          16,
    );

    expect(speakingPeak, lessThanOrEqualTo(budget));
    expect(speakingPeak, greaterThan(thinkingPeak));
    expect(budget, greaterThan(0));
  });
}