import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

class Gate3MainIconButton extends StatelessWidget {
  final IconData icon;
  final String labelFa;
  final VoidCallback onTap;
  final Widget? badge;

  const Gate3MainIconButton({
    super.key,
    required this.icon,
    required this.labelFa,
    required this.onTap,
    this.badge,
  });

  @override
  Widget build(BuildContext context) {
    return InkResponse(
      onTap: onTap,
      radius: 28,
      child: SizedBox(
        width: 62,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.55),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: AppTheme.borderInactive.withOpacity(0.25),
                      width: 1,
                    ),
                    boxShadow: const [
                      BoxShadow(
                        color: Color(0x12000000),
                        blurRadius: 10,
                        offset: Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Icon(
                    icon,
                    size: 22,
                    color: AppTheme.primaryBlack,
                  ),
                ),
                if (badge != null)
                  PositionedDirectional(
                    top: -4,
                    end: -4,
                    child: badge!,
                  ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              labelFa,
              textDirection: TextDirection.rtl,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w600,
                color: Color(0xFF2B2F27),
                height: 1.1,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

