import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config/app_config.dart';
import '../../../features/backend_health/providers/backend_health_provider.dart';
import '../../../shared/widgets/page_header.dart';
import '../providers/settings_provider.dart';

class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(
      text: ref.read(settingsProvider).baseUrl,
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final settings = ref.watch(settingsProvider);
    final health = ref.watch(backendHealthProvider).valueOrNull;

    return ListView(
      children: [
        const PageHeader(
          title: 'Settings',
          subtitle: 'Manage the local backend address and application appearance.',
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _controller,
          decoration: InputDecoration(
            labelText: 'Backend base URL',
            hintText: AppConfig.defaultBaseUrl,
          ),
        ),
        const SizedBox(height: 12),
        FilledButton(
          onPressed: () async {
            await ref
                .read(settingsProvider.notifier)
                .setBaseUrl(_controller.text.trim());
            ref.invalidate(backendHealthProvider);
          },
          child: const Text('Save backend URL'),
        ),
        const SizedBox(height: 8),
        Text(
          'Desktop/local runs should usually use ${AppConfig.localDesktopBaseUrl}. Android emulator runs should use ${AppConfig.androidEmulatorBaseUrl}.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 16),
        SwitchListTile(
          value: settings.themeMode == ThemeMode.dark,
          onChanged: (_) => ref.read(settingsProvider.notifier).toggleTheme(),
          title: const Text('Use dark theme'),
        ),
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Backend connected: ${health?.connected == true ? 'Yes' : 'No'}'),
                Text(
                  'Voice engine: ${health?.voiceModelReady == true ? 'Ready' : 'Not ready'}'
                  '${health == null ? '' : ' (${health.voiceModelMode})'}',
                ),
                Text(
                  'Iris engine: ${health?.irisModelReady == true ? 'Ready' : 'Not ready'}'
                  '${health == null ? '' : ' (${health.irisModelMode})'}',
                ),
                Text(
                  'Development thresholds warning: ${health?.developmentThresholds == true ? 'Visible' : 'Hidden'}',
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
