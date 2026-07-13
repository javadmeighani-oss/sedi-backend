import 'package:flutter/material.dart';

import 'gate3_return_to_latest_button.dart';

/// Message list viewport with a fixed return-to-latest lane when scrolled up.
class Gate3MessageViewport extends StatefulWidget {
  final ScrollController scrollController;
  final VoidCallback onReturnToLatest;
  final String returnTooltip;
  final Widget child;

  static const double visibilityThreshold = 72;
  static const double reservedLaneHeight = 56;
  static const double buttonInsetRight = 12;
  static const double buttonInsetBottom = 12;

  const Gate3MessageViewport({
    super.key,
    required this.scrollController,
    required this.onReturnToLatest,
    required this.returnTooltip,
    required this.child,
  });

  static bool shouldShowReturnButton(ScrollController controller) {
    return controller.hasClients &&
        controller.offset > visibilityThreshold;
  }

  @override
  State<Gate3MessageViewport> createState() => _Gate3MessageViewportState();
}

class _Gate3MessageViewportState extends State<Gate3MessageViewport> {
  @override
  void initState() {
    super.initState();
    widget.scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    widget.scrollController.removeListener(_onScroll);
    super.dispose();
  }

  void _onScroll() {
    if (mounted) setState(() {});
  }

  bool get _showReturnButton =>
      Gate3MessageViewport.shouldShowReturnButton(widget.scrollController);

  @override
  Widget build(BuildContext context) {
    final laneHeight =
        _showReturnButton ? Gate3MessageViewport.reservedLaneHeight : 0.0;

    return Column(
      children: [
        Expanded(child: widget.child),
        AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOutCubic,
          height: laneHeight,
          width: double.infinity,
          child: laneHeight > 0
              ? Align(
                  alignment: Alignment.bottomRight,
                  child: Padding(
                    padding: const EdgeInsets.only(
                      right: Gate3MessageViewport.buttonInsetRight,
                      bottom: Gate3MessageViewport.buttonInsetBottom,
                    ),
                    child: Gate3ReturnToLatestButton(
                      onTap: widget.onReturnToLatest,
                      tooltip: widget.returnTooltip,
                    ),
                  ),
                )
              : null,
        ),
      ],
    );
  }
}
