import 'package:flutter/material.dart';

/// UNREACHABLE_LEGACY — quarantined (R3).
/// Canonical Health is A3 → Lifestyle → Health (`LifestyleHealthPage`).
/// Not wired into [Gate3MainIconRow] or [AppGateRouter].
class Gate3HealthCarePlaceholder extends StatelessWidget {
  const Gate3HealthCarePlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: SafeArea(
        child: Center(
          child: Text(
            'مراقبت سلامت',
            textDirection: TextDirection.rtl,
          ),
        ),
      ),
    );
  }
}

