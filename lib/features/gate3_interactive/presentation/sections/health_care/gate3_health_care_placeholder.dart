import 'package:flutter/material.dart';

/// Gate 3 primary section placeholder.
/// Health UI currently lives in `features/health/`.
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

