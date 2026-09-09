import 'package:flutter/material.dart';

/// Gate 3 primary section placeholder.
/// Lifestyle UI currently lives in `features/lifestyle/`.
class Gate3LifestylePlaceholder extends StatelessWidget {
  const Gate3LifestylePlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: SafeArea(
        child: Center(
          child: Text(
            'سبک زندگی',
            textDirection: TextDirection.rtl,
          ),
        ),
      ),
    );
  }
}

