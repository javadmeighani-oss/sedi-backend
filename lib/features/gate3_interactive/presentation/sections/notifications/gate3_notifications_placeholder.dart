import 'package:flutter/material.dart';

/// Gate 3 primary section placeholder.
/// Real inbox UI currently lives in `features/notification/`.
class Gate3NotificationsPlaceholder extends StatelessWidget {
  const Gate3NotificationsPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: SafeArea(
        child: Center(
          child: Text(
            'اعلان‌ها',
            textDirection: TextDirection.rtl,
          ),
        ),
      ),
    );
  }
}

