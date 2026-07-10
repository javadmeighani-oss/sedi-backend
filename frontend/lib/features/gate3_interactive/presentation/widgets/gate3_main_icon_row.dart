import 'package:flutter/material.dart';

import '../gate3_localization.dart';
import 'gate3_main_icon_button.dart';

class Gate3MainIconRow extends StatelessWidget {
  final VoidCallback onNotifications;
  final VoidCallback onHealthCare;
  final VoidCallback onLifestyle;
  final VoidCallback onGadgets;
  final VoidCallback onHistory;
  final int? unreadCount;
  final String lang;

  const Gate3MainIconRow({
    super.key,
    required this.onNotifications,
    required this.onHealthCare,
    required this.onLifestyle,
    required this.onGadgets,
    required this.onHistory,
    required this.lang,
    this.unreadCount,
  });

  Gate3Localization get _l10n => Gate3Localization(lang);

  Widget? _badge() {
    final c = unreadCount;
    if (c == null || c <= 0) return null;
    final text = c > 99 ? '99+' : '$c';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0xFF111111),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        text,
        textDirection: TextDirection.ltr,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 10,
          fontWeight: FontWeight.w700,
          height: 1.1,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = _l10n;
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Gate3MainIconButton(
          icon: Icons.notifications_outlined,
          label: l10n.notifications,
          onTap: onNotifications,
          badge: _badge(),
        ),
        Gate3MainIconButton(
          icon: Icons.favorite_border,
          label: l10n.healthCare,
          onTap: onHealthCare,
        ),
        Gate3MainIconButton(
          icon: Icons.self_improvement_outlined,
          label: l10n.lifestyle,
          onTap: onLifestyle,
        ),
        Gate3MainIconButton(
          icon: Icons.devices_other_outlined,
          label: l10n.gadgets,
          onTap: onGadgets,
        ),
        Gate3MainIconButton(
          icon: Icons.history,
          label: l10n.history,
          onTap: onHistory,
        ),
      ],
    );
  }
}
