import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../../../core/theme/app_theme.dart';
import '../../../../../core/widgets/app_states/app_empty_state.dart';
import '../../../../../core/widgets/app_states/app_error_state.dart';
import '../../../../../core/widgets/app_states/app_loading_state.dart';
import '../../../logic/lifestyle_section_controller.dart';
import '../../gate3_sections_localization.dart';
import '../../gate3_localization.dart';
import '../../widgets/gate3_section_card.dart';
import '../../widgets/gate3_section_scaffold.dart';
import '../../../../chat/presentation/pages/chat_history_page.dart';

class Gate3LifestyleOverviewPage extends StatefulWidget {
  final String lang;

  const Gate3LifestyleOverviewPage({super.key, required this.lang});

  @override
  State<Gate3LifestyleOverviewPage> createState() =>
      _Gate3LifestyleOverviewPageState();
}

class _Gate3LifestyleOverviewPageState extends State<Gate3LifestyleOverviewPage> {
  late final LifestyleSectionController _controller;

  @override
  void initState() {
    super.initState();
    _controller = LifestyleSectionController(lang: widget.lang);
    _controller.addListener(_onChanged);
    _controller.load();
  }

  @override
  void dispose() {
    _controller.removeListener(_onChanged);
    _controller.dispose();
    super.dispose();
  }

  void _onChanged() {
    if (mounted) setState(() {});
  }

  Gate3SectionsLocalization get l10n => Gate3SectionsLocalization(widget.lang);

  @override
  Widget build(BuildContext context) {
    return Gate3SectionScaffold(
      lang: widget.lang,
      title: l10n.lifestyleTitle,
      isRefreshing: _controller.refreshing,
      onRefresh: () => _controller.load(isRefresh: true),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_controller.loading && _controller.summarySections.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [AppLoadingState(label: l10n.loading)],
      );
    }

    if (_controller.error != null && _controller.summarySections.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          AppErrorState(
            message: _controller.error!,
            onRetry: () => _controller.load(),
          ),
        ],
      );
    }

    final hasData = _controller.summarySections.isNotEmpty ||
        _controller.habits.isNotEmpty ||
        _controller.goals.isNotEmpty;

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        Gate3SectionCard(
          title: Gate3Localization(widget.lang).history,
          child: ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(Gate3Localization(widget.lang).history),
            subtitle: Text(Gate3Localization(widget.lang).historyCardDescription),
            trailing: const Icon(Icons.chevron_right),
            onTap: () {
              Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => ChatHistoryPage(lang: widget.lang),
                ),
              );
            },
          ),
        ),
        if (_controller.lastLoadedAt != null)
          Text(
            '${l10n.lastUpdated}: ${DateFormat.yMMMd().add_Hm().format(_controller.lastLoadedAt!)}',
            style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary),
          ),
        if (!hasData)
          AppEmptyState(
            title: l10n.noLifestyleData,
            subtitle: l10n.lifestyleNotificationsPlanned,
          ),
        ..._summarySections(),
        _listSection(l10n.habits, _controller.habits, 'title', 'description'),
        _listSection(l10n.goals, _controller.goals, 'title', 'description'),
        _listSection(l10n.restrictions, _controller.restrictions, 'title', 'notes'),
        _eventsSection(l10n.dailyPlan, _controller.lifestyleEvents),
        _eventsSection(l10n.lifestyleActivities, _controller.lifestyleDomainEvents),
        Gate3SectionCard(
          title: l10n.weeklyPlan,
          child: _controller.weeklyPlanItems.isEmpty
              ? Text(
                  l10n.weeklySectionEmpty,
                  style: const TextStyle(color: AppTheme.textSecondary),
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: _controller.weeklyPlanItems
                      .map((g) => Text('• ${g['title'] ?? ''}'))
                      .toList(),
                ),
        ),
      ],
    );
  }

  List<Widget> _summarySections() {
    return _controller.summarySections.map((s) {
      final title = s['title']?.toString() ?? '';
      final body = s['body']?.toString() ?? '';
      final items = s['items'] as List?;
      return Gate3SectionCard(
        title: title.isNotEmpty ? title : l10n.nutritionPlan,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (body.isNotEmpty) Text(body),
            if (items != null)
              ...items.map((i) => Text('• ${i.toString()}')),
          ],
        ),
      );
    }).toList();
  }

  Widget _listSection(
    String title,
    List<Map<String, dynamic>> items,
    String primaryKey,
    String secondaryKey,
  ) {
    if (items.isEmpty) return const SizedBox.shrink();
    return Gate3SectionCard(
      title: title,
      child: Column(
        children: items.map((item) {
          return ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(item[primaryKey]?.toString() ?? ''),
            subtitle: item[secondaryKey] != null
                ? Text(item[secondaryKey].toString())
                : null,
          );
        }).toList(),
      ),
    );
  }

  Widget _eventsSection(String title, List<Map<String, dynamic>> events) {
    if (events.isEmpty) return const SizedBox.shrink();
    return Gate3SectionCard(
      title: title,
      child: Column(
        children: events.map((e) {
          return ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(e['title']?.toString() ?? ''),
            subtitle: Text(e['starts_at']?.toString() ?? ''),
          );
        }).toList(),
      ),
    );
  }
}
