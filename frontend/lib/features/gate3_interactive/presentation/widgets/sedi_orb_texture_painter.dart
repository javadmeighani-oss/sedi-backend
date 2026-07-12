import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Deterministic pale capillary texture for the white Sedi eye orb.
///
/// Static geometry — does not animate or rotate between frames.
class SediOrbTexturePainter extends CustomPainter {
  const SediOrbTexturePainter();

  static const _veinColor = Color(0xFFC8B8B5);
  static const _clearCenterRadius = 0.34;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;

    canvas.save();
    canvas.clipPath(
      Path()..addOval(Rect.fromCircle(center: center, radius: radius)),
    );

    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    const branchCount = 11;
    for (var i = 0; i < branchCount; i++) {
      final startAngle = i * (math.pi * 2 / branchCount) + 0.18;
      final startDist = radius * (0.78 + (i % 3) * 0.04);
      var point = center +
          Offset(
            math.cos(startAngle) * startDist,
            math.sin(startAngle) * startDist,
          );
      final path = Path()..moveTo(point.dx, point.dy);

      for (var step = 0; step < 3; step++) {
        final t = (step + 1) / 3;
        final inward = radius * (0.52 - t * 0.22);
        final bend = (i % 2 == 0 ? 0.22 : -0.18) + step * 0.08;
        final angle = startAngle + bend;
        final next = center +
            Offset(math.cos(angle) * inward, math.sin(angle) * inward);

        if (_distanceFromCenter(next, center) < radius * _clearCenterRadius) {
          break;
        }

        final ctrl = Offset(
          (point.dx + next.dx) / 2 + math.sin(angle) * 3,
          (point.dy + next.dy) / 2 - math.cos(angle) * 3,
        );
        path.quadraticBezierTo(ctrl.dx, ctrl.dy, next.dx, next.dy);
        point = next;
      }

      paint
        ..color = _veinColor.withOpacity(0.05 + (i % 4) * 0.015)
        ..strokeWidth = 0.65 + (i % 3) * 0.15;
      canvas.drawPath(path, paint);
    }

    canvas.restore();
  }

  double _distanceFromCenter(Offset point, Offset center) {
    return (point - center).distance;
  }

  @override
  bool shouldRepaint(covariant SediOrbTexturePainter oldDelegate) => false;
}
