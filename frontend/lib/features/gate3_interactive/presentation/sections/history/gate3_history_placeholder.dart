import 'package:flutter/material.dart';

/// Gate 3 primary section placeholder.
/// History UI currently lives in `features/chat/presentation/pages/chat_history_page.dart`.
class Gate3HistoryPlaceholder extends StatelessWidget {
  const Gate3HistoryPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: SafeArea(
        child: Center(
          child: Text(
            'تاریخچه',
            textDirection: TextDirection.rtl,
          ),
        ),
      ),
    );
  }
}

