import 'dart:math' as math;

/// Authoritative layout geometry for the Gate 3 radial spectrum visualizer.
///
/// Layout resolution and [SediAudioVisualizerPainter] share the same resolved
/// bar extension, glow paint radius, and shader envelope values.
class SediAudioVisualizerGeometry {
  SediAudioVisualizerGeometry._();

  static const double barExtensionScale = 14.0;
  static const double barLengthFloor = 3.0;
  static const double barLengthMinBase = 1.2;
  static const double barLengthMinAmplitudeScale = 0.8;

  static const double maxBarStrokeWidth = 1.0;
  static const double strokeSafetyMargin = maxBarStrokeWidth / 2;
  static const double antiAliasSafetyMargin = 0.5;

  static const double glowPaintRadiusBeyondSpectrum = 6.0;
  static const double glowShaderExtraBeyondBarExtension = 4.0;

  /// Highest steady-state amplitude target (thinking).
  static const double peakAmplitude = 0.92;

  static const double preferredSpectrumOffset = 10.0;
  static const double minSpectrumOffset = 7.0;
  static const double maxSpectrumOffset = 18.0;
  static const double degradedMinSpectrumOffset = 3.0;

  static const double sideInset = 8.0;
  static const double verticalInset = 6.0;

  static double maxBarLength(double amplitude, {double barExtensionFactor = 1}) {
    final factor = barExtensionFactor.clamp(0.0, 1.0);
    return barLengthFloor + amplitude * barExtensionScale * factor;
  }

  static double minBarLength(double amplitude, {double barExtensionFactor = 1}) {
    final factor = barExtensionFactor.clamp(0.0, 1.0);
    return barLengthMinBase + amplitude * barLengthMinAmplitudeScale * factor;
  }

  /// Radial bar + stroke envelope measured outward from the spectrum ring.
  static double radialBarOutwardExtent(
    double amplitude, {
    double barExtensionFactor = 1,
  }) {
    return maxBarLength(amplitude, barExtensionFactor: barExtensionFactor) +
        strokeSafetyMargin +
        antiAliasSafetyMargin;
  }

  /// Complete outward paint budget from [spectrumRadius], matching the painter.
  static double maximumPaintedOutwardExtent(
    double amplitude, {
    double barExtensionFactor = 1,
    double glowPaintRadius = glowPaintRadiusBeyondSpectrum,
    double glowShaderExtra = glowShaderExtraBeyondBarExtension,
  }) {
    final barOutward = radialBarOutwardExtent(
      amplitude,
      barExtensionFactor: barExtensionFactor,
    );
    return math.max(
      barOutward + glowShaderExtra,
      glowPaintRadius,
    );
  }

  static double maximumPaintedOutwardExtentAtPeak({
    double barExtensionFactor = 1,
    double glowPaintRadius = glowPaintRadiusBeyondSpectrum,
    double glowShaderExtra = glowShaderExtraBeyondBarExtension,
  }) {
    return maximumPaintedOutwardExtent(
      peakAmplitude,
      barExtensionFactor: barExtensionFactor,
      glowPaintRadius: glowPaintRadius,
      glowShaderExtra: glowShaderExtra,
    );
  }

  /// Geometry-derived preferred visualizer canvas height for the approved orb.
  static double preferredCanvasHeight(double orbBodyRadius) {
    final spectrumRadius = orbBodyRadius + preferredSpectrumOffset;
    final outward = maximumPaintedOutwardExtentAtPeak();
    return 2 * (verticalInset + spectrumRadius + outward);
  }

  /// Minimum canvas that keeps the orb outside the spectrum baseline.
  static double minimumCanvasHeight(double orbBodyRadius) {
    final spectrumRadius = orbBodyRadius + degradedMinSpectrumOffset;
    final outward = maximumPaintedOutwardExtent(
      peakAmplitude,
      barExtensionFactor: 0,
      glowPaintRadius: 0,
      glowShaderExtra: 0,
    );
    return 2 * (verticalInset + spectrumRadius + outward);
  }

  static double _safeClamp(double value, double lower, double upper) {
    if (!value.isFinite) return lower;
    if (lower > upper) return upper;
    return value.clamp(lower, upper);
  }

  static double _availableCanvasRadius({
    required double width,
    required double containerHeight,
  }) {
    final halfHeight = (containerHeight / 2) - verticalInset;
    final halfWidth = (width / 2) - sideInset;
    return math.max(0, math.min(halfHeight, halfWidth));
  }

  static bool _layoutFits({
    required double canvasRadius,
    required double spectrumRadius,
    required double amplitude,
    required double barExtensionFactor,
    required double glowPaintRadius,
    required double glowShaderExtra,
  }) {
    if (canvasRadius <= 0 || spectrumRadius <= 0) return false;
    final outward = maximumPaintedOutwardExtent(
      amplitude,
      barExtensionFactor: barExtensionFactor,
      glowPaintRadius: glowPaintRadius,
      glowShaderExtra: glowShaderExtra,
    );
    return spectrumRadius + outward <= canvasRadius + 1e-6;
  }

  static SediVisualizerLayout resolveLayout({
    required double width,
    required double containerHeight,
    required double orbBodyRadius,
    double amplitude = peakAmplitude,
  }) {
    final canvasRadius = _availableCanvasRadius(
      width: width,
      containerHeight: containerHeight,
    );

    final minSpectrum = orbBodyRadius + degradedMinSpectrumOffset;
    final nominalMaxSpectrum = orbBodyRadius + maxSpectrumOffset;
    final preferredSpectrum = orbBodyRadius + preferredSpectrumOffset;

    var spectrumRadius = _safeClamp(
      preferredSpectrum,
      minSpectrum,
      nominalMaxSpectrum,
    );

    var barExtensionFactor = 1.0;
    var glowPaintRadius = glowPaintRadiusBeyondSpectrum;
    var glowShaderExtra = glowShaderExtraBeyondBarExtension;

    bool fits() => _layoutFits(
          canvasRadius: canvasRadius,
          spectrumRadius: spectrumRadius,
          amplitude: amplitude,
          barExtensionFactor: barExtensionFactor,
          glowPaintRadius: glowPaintRadius,
          glowShaderExtra: glowShaderExtra,
        );

    for (var pass = 0; pass < 240 && !fits(); pass++) {
      if (barExtensionFactor > 0) {
        barExtensionFactor = math.max(0, barExtensionFactor - 0.05);
        continue;
      }
      if (glowShaderExtra > 0) {
        glowShaderExtra = math.max(0, glowShaderExtra - 1);
        continue;
      }
      if (glowPaintRadius > 0) {
        glowPaintRadius = math.max(0, glowPaintRadius - 1);
        continue;
      }
      if (spectrumRadius > orbBodyRadius + 2) {
        spectrumRadius = math.max(orbBodyRadius + 2, spectrumRadius - 0.5);
        continue;
      }
      break;
    }

    final baselineOnly = maximumPaintedOutwardExtent(
      amplitude,
      barExtensionFactor: 0,
      glowPaintRadius: 0,
      glowShaderExtra: 0,
    );
    final maxSpectrumForCanvas = math.max(
      orbBodyRadius + 2,
      canvasRadius - baselineOnly,
    );
    spectrumRadius = _safeClamp(
      spectrumRadius,
      orbBodyRadius + 2,
      math.max(orbBodyRadius + 2, maxSpectrumForCanvas),
    );

    if (!_layoutFits(
      canvasRadius: canvasRadius,
      spectrumRadius: spectrumRadius,
      amplitude: amplitude,
      barExtensionFactor: barExtensionFactor,
      glowPaintRadius: glowPaintRadius,
      glowShaderExtra: glowShaderExtra,
    )) {
      final availableOutward = math.max(0, canvasRadius - spectrumRadius);
      final barBudget = availableOutward -
          glowPaintRadius -
          strokeSafetyMargin -
          antiAliasSafetyMargin -
          barLengthFloor;
      if (barBudget <= 0 || amplitude <= 0) {
        barExtensionFactor = 0;
      } else {
        barExtensionFactor = _safeClamp(
          barBudget / (amplitude * barExtensionScale),
          0,
          1,
        );
      }
      glowShaderExtra = 0;
      glowPaintRadius = math.min(
        glowPaintRadius,
        math.max(0, availableOutward - radialBarOutwardExtent(
              amplitude,
              barExtensionFactor: barExtensionFactor,
            )),
      );
    }

    spectrumRadius = _safeClamp(
      spectrumRadius,
      orbBodyRadius + 2,
      math.max(orbBodyRadius + 2, canvasRadius),
    );
    barExtensionFactor = barExtensionFactor.clamp(0.0, 1.0);
    glowPaintRadius = glowPaintRadius.clamp(0.0, glowPaintRadiusBeyondSpectrum);
    glowShaderExtra =
        glowShaderExtra.clamp(0.0, glowShaderExtraBeyondBarExtension);

    return SediVisualizerLayout(
      spectrumRadius: spectrumRadius,
      barExtensionFactor: barExtensionFactor,
      glowPaintRadiusBeyondSpectrum: glowPaintRadius,
      glowShaderExtraBeyondBarExtension: glowShaderExtra,
    );
  }

  /// Verifies the radial spectrum stays inside the visualizer canvas.
  static bool paintedExtentFits({
    required double width,
    required double containerHeight,
    required SediVisualizerLayout layout,
    required double amplitude,
  }) {
    if (width <= 0 || containerHeight <= 0) return false;
    if (!layout.spectrumRadius.isFinite || layout.spectrumRadius <= 0) {
      return false;
    }

    final canvasRadius = _availableCanvasRadius(
      width: width,
      containerHeight: containerHeight,
    );
    return _layoutFits(
      canvasRadius: canvasRadius,
      spectrumRadius: layout.spectrumRadius,
      amplitude: amplitude,
      barExtensionFactor: layout.barExtensionFactor,
      glowPaintRadius: layout.glowPaintRadiusBeyondSpectrum,
      glowShaderExtra: layout.glowShaderExtraBeyondBarExtension,
    );
  }
}

class SediVisualizerLayout {
  final double spectrumRadius;
  final double barExtensionFactor;
  final double glowPaintRadiusBeyondSpectrum;
  final double glowShaderExtraBeyondBarExtension;

  const SediVisualizerLayout({
    required this.spectrumRadius,
    required this.barExtensionFactor,
    required this.glowPaintRadiusBeyondSpectrum,
    required this.glowShaderExtraBeyondBarExtension,
  });
}
