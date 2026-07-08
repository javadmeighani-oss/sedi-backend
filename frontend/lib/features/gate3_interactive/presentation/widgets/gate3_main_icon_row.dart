import 'package:flutter/material.dart';

import 'gate3_main_icon_button.dart';

class Gate3MainIconRow extends StatelessWidget {
  final VoidCallback onNotifications;
  final VoidCallback onHealthCare;
  final VoidCallback onLifestyle;
  final VoidCallback onGadgets;
  final VoidCallback onHistory;
  final int? unreadCount;

  const Gate3MainIconRow({
    super.key,
    required this.onNotifications,
    required this.onHealthCare,
    required this.onLifestyle,
    required this.onGadgets,
    required this.onHistory,
    this.unreadCount,
  });

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
    return Directionality(
      textDirection: TextDirection.rtl,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Gate3MainIconButton(
            icon: Icons.notifications_outlined,
            labelFa: 'اعلان‌ها',
            onTap: onNotifications,
            badge: _badge(),
          ),
          Gate3MainIconButton(
            icon: Icons.favorite_border,
            labelFa: 'مراقبت سلامت',
            onTap: onHealthCare,
          ),
          Gate3MainIconButton(
            icon: Icons.self_improvement_outlined,
            labelFa: 'سبک زندگی',
            onTap: onLifestyle,
          ),
          Gate3MainIconButton(
            icon: Icons.devices_other_outlined,
            labelFa: 'گجت‌ها',
            onTap: onGadgets,
          ),
          Gate3MainIconButton(
            icon: Icons.history,
            labelFa: 'تاریخچه',
            onTap: onHistory,
          ),
        ],
      ),
    );
  }
}

