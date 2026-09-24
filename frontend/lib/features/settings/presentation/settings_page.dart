import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config/app_config.dart';
import '../../../core/theme/app_colours.dart';
import '../../../shared/widgets/page_header.dart';
import '../../backend_health/models/backend_health_status.dart';
import '../../backend_health/providers/backend_health_provider.dart';
import '../providers/settings_provider.dart';

class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _baseUrlController;
  late final FocusNode _baseUrlFocusNode;
  bool _saving = false;
  bool _testing = false;

  @override
  void initState() {
    super.initState();
    _baseUrlController = TextEditingController(
      text: ref.read(settingsProvider).baseUrl,
    );
    _baseUrlFocusNode = FocusNode();
  }

  @override
  void dispose() {
    _baseUrlController.dispose();
    _baseUrlFocusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<SettingsState>(settingsProvider, (previous, next) {
      if (!_baseUrlFocusNode.hasFocus &&
          _baseUrlController.text != next.baseUrl) {
        _replaceBaseUrlText(next.baseUrl);
      }
    });

    final settings = ref.watch(settingsProvider);
    final healthAsync = ref.watch(backendHealthProvider);
    final health = healthAsync.valueOrNull;
    final compact = MediaQuery.sizeOf(context).width < 700;

    return ListView(
      children: [
        const PageHeader(
          title: 'Settings',
          subtitle: 'Configure this installation and check local services.',
        ),
        const SizedBox(height: 20),
        _SettingsSection(
          icon: Icons.dns_rounded,
          title: 'Local backend',
          description:
              'Set the address of the biometric service. A blank value uses '
              'the platform default. Phones and other computers need a '
              'reachable server address; deployed web builds must use HTTPS.',
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextFormField(
                  controller: _baseUrlController,
                  focusNode: _baseUrlFocusNode,
                  decoration: const InputDecoration(
                    labelText: 'Backend URL',
                    hintText: 'http://127.0.0.1:8000/api/v1',
                    prefixIcon: Icon(Icons.link_rounded),
                  ),
                  keyboardType: TextInputType.url,
                  textInputAction: TextInputAction.done,
                  autocorrect: false,
                  enableSuggestions: false,
                  validator: AppConfig.validateBaseUrl,
                  onFieldSubmitted: (_) => _saveAndTest(),
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 12,
                  runSpacing: 10,
                  children: [
                    FilledButton.icon(
                      onPressed: _saving || _testing ? null : _saveAndTest,
                      icon: _saving
                          ? const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.save_rounded),
                      label: Text(
                        _saving ? 'Saving and testing…' : 'Save and test',
                      ),
                    ),
                    OutlinedButton.icon(
                      onPressed: _saving || _testing ? null : _testConnection,
                      icon: _testing
                          ? const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.sync_rounded),
                      label: Text(_testing ? 'Testing…' : 'Test connection'),
                    ),
                    TextButton.icon(
                      onPressed: _saving || _testing
                          ? null
                          : () {
                              _replaceBaseUrlText(AppConfig.defaultBaseUrl);
                              _saveAndTest();
                            },
                      icon: const Icon(Icons.restart_alt_rounded),
                      label: const Text('Use default'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        _SettingsSection(
          icon: Icons.palette_outlined,
          title: 'Appearance',
          description: 'Choose how the interface theme is selected.',
          child: Align(
            alignment: Alignment.centerLeft,
            child: SegmentedButton<ThemeMode>(
              segments: const [
                ButtonSegment(
                  value: ThemeMode.system,
                  icon: Icon(Icons.brightness_auto_rounded),
                  label: Text('System'),
                ),
                ButtonSegment(
                  value: ThemeMode.light,
                  icon: Icon(Icons.light_mode_rounded),
                  label: Text('Light'),
                ),
                ButtonSegment(
                  value: ThemeMode.dark,
                  icon: Icon(Icons.dark_mode_rounded),
                  label: Text('Dark'),
                ),
              ],
              selected: {settings.themeMode},
              onSelectionChanged: (selection) {
                ref
                    .read(settingsProvider.notifier)
                    .setThemeMode(selection.first);
              },
              showSelectedIcon: false,
            ),
          ),
        ),
        const SizedBox(height: 16),
        _SettingsSection(
          icon: Icons.monitor_heart_outlined,
          title: 'Service status',
          description:
              'Live readiness reported by the configured backend address.',
          child: Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _StatusItem(
                width: compact ? double.infinity : 210,
                label: 'Backend',
                detail: healthAsync.isLoading
                    ? 'Checking'
                    : health?.connected == true
                    ? 'Connected'
                    : health?.reachable == true
                    ? 'Starting models'
                    : 'Offline',
                ready: health?.connected == true,
                loading: healthAsync.isLoading,
              ),
              _StatusItem(
                width: compact ? double.infinity : 210,
                label: 'Voice model',
                detail: _modelDetail(health, voice: true),
                ready: health?.voiceModelReady == true,
                loading: healthAsync.isLoading,
              ),
              _StatusItem(
                width: compact ? double.infinity : 210,
                label: 'Iris model',
                detail: _modelDetail(health, voice: false),
                ready: health?.irisModelReady == true,
                loading: healthAsync.isLoading,
              ),
            ],
          ),
        ),
      ],
    );
  }

  String _modelDetail(BackendHealthStatus? health, {required bool voice}) {
    if (health == null || !health.reachable) return 'Unavailable';
    final ready = voice ? health.voiceModelReady : health.irisModelReady;
    final label = voice ? health.voiceModelLabel : health.irisModelLabel;
    return ready ? label : 'Not ready';
  }

  Future<void> _saveAndTest() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _saving = true);
    try {
      await ref
          .read(settingsProvider.notifier)
          .setBaseUrl(_baseUrlController.text);
      final savedUrl = ref.read(settingsProvider).baseUrl;
      _replaceBaseUrlText(savedUrl);
      ref.invalidate(backendHealthProvider);
      final health = await ref.read(backendHealthProvider.future);
      if (!mounted) return;
      _showConnectionResult(
        health,
        successMessage: 'Settings saved. Backend is connected.',
        failureMessage:
            'Settings saved, but the backend could not be reached at $savedUrl.',
      );
    } catch (error) {
      if (!mounted) return;
      _showMessage('Could not save settings: $error', error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _testConnection() async {
    setState(() => _testing = true);
    try {
      final health = await ref
          .read(backendHealthProvider.notifier)
          .refreshStatus();
      if (!mounted) return;
      _showConnectionResult(
        health,
        successMessage: 'Backend connection is working.',
        failureMessage: 'The configured backend is currently unreachable.',
      );
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  void _showConnectionResult(
    BackendHealthStatus health, {
    required String successMessage,
    required String failureMessage,
  }) {
    _showMessage(
      health.connected ? successMessage : failureMessage,
      error: !health.connected,
    );
  }

  void _showMessage(String message, {bool error = false}) {
    final messenger = ScaffoldMessenger.of(context);
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: error ? AppColours.error : AppColours.success,
        ),
      );
  }

  void _replaceBaseUrlText(String value) {
    _baseUrlController.value = TextEditingValue(
      text: value,
      selection: TextSelection.collapsed(offset: value.length),
    );
  }
}

class _SettingsSection extends StatelessWidget {
  const _SettingsSection({
    required this.icon,
    required this.title,
    required this.description,
    required this.child,
  });

  final IconData icon;
  final String title;
  final String description;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(22),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(icon, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 4),
                      Text(description),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            child,
          ],
        ),
      ),
    );
  }
}

class _StatusItem extends StatelessWidget {
  const _StatusItem({
    required this.width,
    required this.label,
    required this.detail,
    required this.ready,
    required this.loading,
  });

  final double width;
  final String label;
  final String detail;
  final bool ready;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final colour = ready ? AppColours.success : AppColours.warning;
    return Container(
      width: width,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          if (loading)
            const SizedBox.square(
              dimension: 20,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          else
            Icon(
              ready ? Icons.check_circle_rounded : Icons.warning_amber_rounded,
              color: colour,
            ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: Theme.of(context).textTheme.labelLarge),
                Text(detail, maxLines: 1, overflow: TextOverflow.ellipsis),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
