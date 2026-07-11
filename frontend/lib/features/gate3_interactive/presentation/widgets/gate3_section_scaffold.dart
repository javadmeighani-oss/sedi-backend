import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../gate3_sections_localization.dart';

/// Shared scaffold for Gate 3 destination section pages.
class Gate3SectionScaffold extends StatelessWidget {
  final String lang;
  final String title;
  final Widget body;
  final VoidCallback? onRefresh;
  final bool isRefreshing;

  const Gate3SectionScaffold({
    super.key,
    required this.lang,
    required this.title,
    required this.body,
    this.onRefresh,
    this.isRefreshing = false,
  });

  @override
  Widget build(BuildContext context) {
    final l10n = Gate3SectionsLocalization(lang);
    final isRtl = l10n.isRtl;

    Widget content = body;
    if (onRefresh != null) {
      content = RefreshIndicator(
        color: AppTheme.gate2ButtonOlive,
        onRefresh: () async => onRefresh!(),
        child: content,
      );
    }

    return Directionality(
      textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: AppTheme.gate3PaleOliveBackground,
        appBar: AppBar(
          backgroundColor: AppTheme.gate3PaleOliveBackground,
          elevation: 0,
          scrolledUnderElevation: 0,
          foregroundColor: AppTheme.textPrimary,
          leading: IconButton(
            icon: Icon(isRtl ? Icons.arrow_forward_rounded : Icons.arrow_back_rounded),
            tooltip: l10n.backTooltip,
            onPressed: () => Navigator.of(context).pop(),
          ),
          title: Text(
            title,
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: AppTheme.textPrimary,
            ),
          ),
          actions: [
            if (onRefresh != null)
              IconButton(
                icon: isRefreshing
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.refresh_rounded),
                tooltip: l10n.refresh,
                onPressed: isRefreshing ? null : onRefresh,
              ),
          ],
        ),
        body: SafeArea(child: content),
      ),
    );
  }
}
