import 'dart:math' as math;

import 'sedi_audio_visualizer_geometry.dart';

/// Responsive vertical budget for the Gate 3 interactive page.
class Gate3VerticalLayout {
  Gate3VerticalLayout._();

  /// Icon row intrinsic height (44 icon + 6 gap + ~22 label).
  static const double iconRowHeight = 72;

  /// Top icon padding and spacer below the row.
  static const double topSectionSpacing = 12;

  static const double belowOrbSpacing = 8;

  static const double chatPanelOuterPadding = 8;

  /// Minimum scrollable message viewport inside the chat panel.
  static const double minMessageViewportHeight = 96;

  /// Composer card margin, field, and toolbar minimum.
  static const double composerMinimumHeight = 108;

  static double reservedBelowVisualizerHeight({
    double belowOrbSpacing = Gate3VerticalLayout.belowOrbSpacing,
  }) {
    return belowOrbSpacing +
        chatPanelOuterPadding +
        minMessageViewportHeight +
        composerMinimumHeight;
  }

  static double reservedAboveChatPanelHeight({
    double belowOrbSpacing = Gate3VerticalLayout.belowOrbSpacing,
  }) {
    return iconRowHeight +
        topSectionSpacing +
        reservedBelowVisualizerHeight(belowOrbSpacing: belowOrbSpacing);
  }

  /// Chooses a visualizer canvas height without shrinking the composer.
  static double resolveVisualizerCanvasHeight({
    required double availableSafeHeight,
    required double orbBodyRadius,
    double belowOrbSpacing = Gate3VerticalLayout.belowOrbSpacing,
  }) {
    if (!availableSafeHeight.isFinite || availableSafeHeight <= 0) {
      return SediAudioVisualizerGeometry.minimumCanvasHeight(orbBodyRadius);
    }

    final preferred =
        SediAudioVisualizerGeometry.preferredCanvasHeight(orbBodyRadius);
    final minimum =
        SediAudioVisualizerGeometry.minimumCanvasHeight(orbBodyRadius);

    final maxCanvas = availableSafeHeight -
        iconRowHeight -
        topSectionSpacing -
        reservedBelowVisualizerHeight(belowOrbSpacing: belowOrbSpacing);

    final upper = math.max(minimum, maxCanvas);
    return _safeClamp(preferred, minimum, upper);
  }

  static double _safeClamp(double value, double lower, double upper) {
    if (!value.isFinite) return lower;
    if (lower > upper) return upper;
    return value.clamp(lower, upper);
  }
}
