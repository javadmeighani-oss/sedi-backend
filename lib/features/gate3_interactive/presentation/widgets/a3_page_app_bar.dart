import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

/// Shared A3 destination Back control.
///
/// Presentation only: uses Material [BackButton] / [BackButtonIcon] so leading
/// placement follows ambient [Directionality] (LTR/RTL). One activation pops
/// exactly one route via the ambient Navigator — no product/business authority.
class A3BackButton extends StatelessWidget {
  const A3BackButton({super.key});

  @override
  Widget build(BuildContext context) {
    return const BackButton(
      color: AppTheme.textPrimary,
    );
  }
}

/// Shared A3 destination [AppBar] with the canonical leading Back control.
///
/// Does not own locale, subject, API, or routing policy beyond Material defaults.
class A3PageAppBar extends StatelessWidget implements PreferredSizeWidget {
  final Widget title;
  final Color backgroundColor;
  final Color foregroundColor;
  final List<Widget>? actions;

  const A3PageAppBar({
    super.key,
    required this.title,
    this.backgroundColor = AppTheme.gate3PaleOliveBackground,
    this.foregroundColor = AppTheme.textPrimary,
    this.actions,
  });

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) {
    return AppBar(
      leading: const A3BackButton(),
      title: title,
      backgroundColor: backgroundColor,
      foregroundColor: foregroundColor,
      elevation: 0,
      actions: actions,
    );
  }
}
