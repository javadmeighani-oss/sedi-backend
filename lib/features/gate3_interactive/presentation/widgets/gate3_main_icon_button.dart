import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

class Gate3MainIconButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Widget? badge;
  final bool plainIcon;

  const Gate3MainIconButton({
    super.key,
    required this.icon,
    required this.label,
    required this.onTap,
    this.badge,
    this.plainIcon = false,
  });

  @override
  Widget build(BuildContext context) {
    return InkResponse(
      onTap: onTap,
      radius: 28,
      child: SizedBox(
        width: plainIcon ? 56 : 72,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Stack(
              clipBehavior: Clip.none,
              alignment: Alignment.center,
              children: [
                if (plainIcon)
                  SizedBox(
                    width: 44,
                    height: 44,
                    child: Icon(
                      icon,
                      size: 24,
                      color: AppTheme.primaryBlack,
                    ),
                  )
                else
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.55),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(
                        color: AppTheme.borderInactive.withOpacity(0.25),
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
              label,
              maxLines: 2,
              overflow: TextOverflow.visible,
              softWrap: true,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: plainIcon ? 10.5 : 10.5,
                fontWeight: FontWeight.w600,
                color: const Color(0xFF2B2F27),
                height: 1.15,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
