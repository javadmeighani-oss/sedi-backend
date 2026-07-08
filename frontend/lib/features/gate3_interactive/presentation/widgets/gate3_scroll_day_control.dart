import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

class Gate3ScrollDayControl extends StatelessWidget {
  const Gate3ScrollDayControl({super.key});

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      ignoring: true, // UI-only placeholder for V1
      child: Container(
        width: 34,
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.35),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color: AppTheme.borderInactive.withOpacity(0.22),
            width: 1,
          ),
        ),
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 6),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: const [
            Icon(Icons.calendar_month_outlined, size: 16, color: AppTheme.primaryBlack),
            RotatedBox(
              quarterTurns: 3,
              child: Text(
                '۱ روز گذشته',
                textDirection: TextDirection.rtl,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF2B2F27),
                ),
              ),
            ),
            Icon(Icons.more_vert, size: 16, color: AppTheme.iconInactive),
          ],
        ),
      ),
    );
  }
}

