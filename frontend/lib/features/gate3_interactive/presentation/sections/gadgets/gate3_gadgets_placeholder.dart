import 'package:flutter/material.dart';

/// Gate 3 primary section placeholder.
/// Gadgets UI currently lives in `features/devices/`.
class Gate3GadgetsPlaceholder extends StatelessWidget {
  const Gate3GadgetsPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: SafeArea(
        child: Center(
          child: Text(
            'گجت‌ها',
            textDirection: TextDirection.rtl,
          ),
        ),
      ),
    );
  }
}

