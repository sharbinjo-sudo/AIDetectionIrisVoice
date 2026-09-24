import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';

import '../../../core/errors/app_exception.dart';
import '../../../core/networking/dio_client.dart';
import '../../../core/routing/route_names.dart';
import '../../../core/storage/secure_storage_service.dart';
import '../../../core/theme/app_colours.dart';
import '../../../core/widgets/primary_button.dart';
import '../data/banking_auth_repository.dart';

enum BankingAuthMode { login, register }

class BankingAuthPage extends ConsumerStatefulWidget {
  const BankingAuthPage.login({super.key}) : mode = BankingAuthMode.login;

  const BankingAuthPage.register({super.key}) : mode = BankingAuthMode.register;

  final BankingAuthMode mode;

  @override
  ConsumerState<BankingAuthPage> createState() => _BankingAuthPageState();
}

class _BankingAuthPageState extends ConsumerState<BankingAuthPage> {
  final _formKey = GlobalKey<FormState>();
  final _customerIdController = TextEditingController();
  final _nameController = TextEditingController();
  final _mobileController = TextEditingController();
  final _pinController = TextEditingController();
  bool _submitting = false;
  String? _errorMessage;

  bool get _registering => widget.mode == BankingAuthMode.register;

  @override
  void initState() {
    super.initState();
    if (!_registering) {
      Future<void>.microtask(() async {
        final customerId = await ref
            .read(secureStorageProvider)
            .readBankingCustomerId();
        if (mounted && _customerIdController.text.isEmpty) {
          _customerIdController.text =
              customerId != null && RegExp(r'^[0-9]+$').hasMatch(customerId)
              ? customerId
              : '';
        }
      });
    }
  }

  @override
  void dispose() {
    _customerIdController.dispose();
    _nameController.dispose();
    _mobileController.dispose();
    _pinController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting || _formKey.currentState?.validate() != true) return;

    FocusScope.of(context).unfocus();
    setState(() {
      _submitting = true;
      _errorMessage = null;
    });
    try {
      final repository = BankingAuthRepository(ref.read(dioProvider));
      final session = _registering
          ? await repository.register(
              fullName: _nameController.text.trim(),
              mobileNumber: _mobileController.text.trim(),
              pin: _pinController.text,
            )
          : await repository.login(
              customerId: _customerIdController.text.trim(),
              pin: _pinController.text,
            );

      if (session.token.isEmpty ||
          session.customerId.isEmpty ||
          session.biometricUserId.isEmpty ||
          !const [
            'BIOMETRIC_ENROLLMENT',
            'BIOMETRIC_VERIFICATION',
          ].contains(session.nextStep)) {
        throw AppException(
          message: 'The server returned an incomplete authentication session.',
        );
      }
      await ref
          .read(secureStorageProvider)
          .saveBankingSession(
            token: session.token,
            customerId: session.customerId,
            biometricUserId: session.biometricUserId,
          );

      if (!mounted) return;
      if (_registering) {
        await _showGeneratedIdentifiers(session);
        if (!mounted) return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _registering
                ? 'Account created. Enroll your iris and voice to finish registration.'
                : session.nextStep == 'BIOMETRIC_ENROLLMENT'
                ? 'Biometric enrollment is not completed. Continue enrollment to finish registration.'
                : 'Credentials accepted. Complete biometric verification.',
          ),
        ),
      );
      context.goNamed(
        RouteNames.irl,
        queryParameters: {
          'flow': session.nextStep == 'BIOMETRIC_ENROLLMENT'
              ? 'enrollment'
              : 'verification',
          'user': session.biometricUserId,
          'eye': session.enrolledEyeSide,
        },
      );
    } on AppException catch (error) {
      if (!mounted) return;
      setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _showGeneratedIdentifiers(BankingAuthSession session) async {
    final details = session.customerId;
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => AlertDialog(
        icon: const Icon(Icons.check_circle_rounded, color: Colors.green),
        title: const Text('Account created'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Save your customer ID. Use it with your PIN to log in.',
            ),
            const SizedBox(height: 18),
            Text('Customer ID', style: Theme.of(context).textTheme.labelLarge),
            SelectableText(
              session.customerId,
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ],
        ),
        actions: [
          TextButton.icon(
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: details));
              if (mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Customer ID copied.')),
                );
              }
            },
            icon: const Icon(Icons.copy_rounded),
            label: const Text('Copy customer ID'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Continue to biometric enrollment'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final compact = MediaQuery.sizeOf(context).width < 850;
    final introduction = _AuthIntroduction(registering: _registering);
    final form = _AuthForm(
      formKey: _formKey,
      registering: _registering,
      customerIdController: _customerIdController,
      nameController: _nameController,
      mobileController: _mobileController,
      pinController: _pinController,
      submitting: _submitting,
      errorMessage: _errorMessage,
      onSubmit: _submit,
    );

    return ListView(
      children: [
        Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1040),
            child: compact
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [introduction, const SizedBox(height: 20), form],
                  )
                : Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: introduction),
                      const SizedBox(width: 28),
                      SizedBox(width: 480, child: form),
                    ],
                  ),
          ),
        ),
      ],
    );
  }
}

class _AuthIntroduction extends StatelessWidget {
  const _AuthIntroduction({required this.registering});

  final bool registering;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColours.deepNavy,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              registering
                  ? Icons.person_add_alt_1_rounded
                  : Icons.lock_person_rounded,
              color: Colors.white,
              size: 38,
            ),
            const SizedBox(height: 22),
            Text(
              registering ? 'Create your account' : 'Welcome back',
              style: Theme.of(
                context,
              ).textTheme.headlineMedium?.copyWith(color: Colors.white),
            ),
            const SizedBox(height: 12),
            Text(
              registering
                  ? 'Enter your name and mobile number, then choose a 4-digit PIN. Your customer ID is generated automatically.'
                  : 'Enter your customer ID and PIN, then complete biometric verification.',
              style: const TextStyle(color: Colors.white, height: 1.5),
            ),
            const SizedBox(height: 26),
            _AuthStep(
              number: '1',
              text: registering
                  ? 'Choose a PIN and receive your customer ID'
                  : 'Enter your customer ID and PIN',
            ),
            const SizedBox(height: 14),
            _AuthStep(
              number: '2',
              text: registering
                  ? 'Enroll iris and voice templates'
                  : 'Capture a fresh iris sample and voice recording',
            ),
            const SizedBox(height: 14),
            _AuthStep(
              number: '3',
              text: registering
                  ? 'Finish secure account setup'
                  : 'Continue after biometric verification',
            ),
          ],
        ),
      ),
    );
  }
}

class _AuthStep extends StatelessWidget {
  const _AuthStep({required this.number, required this.text});

  final String number;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        CircleAvatar(
          radius: 15,
          backgroundColor: Colors.white.withValues(alpha: 0.14),
          child: Text(number, style: const TextStyle(color: Colors.white)),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(text, style: const TextStyle(color: Colors.white)),
        ),
      ],
    );
  }
}

class _AuthForm extends StatelessWidget {
  const _AuthForm({
    required this.formKey,
    required this.registering,
    required this.customerIdController,
    required this.nameController,
    required this.mobileController,
    required this.pinController,
    required this.submitting,
    this.errorMessage,
    required this.onSubmit,
  });

  final GlobalKey<FormState> formKey;
  final bool registering;
  final TextEditingController customerIdController;
  final TextEditingController nameController;
  final TextEditingController mobileController;
  final TextEditingController pinController;
  final bool submitting;
  final String? errorMessage;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Form(
          key: formKey,
          child: AutofillGroup(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  registering ? 'Register' : 'Login',
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
                if (errorMessage != null) ...[
                  const SizedBox(height: 12),
                  Semantics(
                    liveRegion: true,
                    child: Text(
                      errorMessage!,
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 6),
                Text(
                  registering
                      ? 'Create your customer profile.'
                      : 'Sign in to verify your identity or finish an incomplete enrollment. Use your existing customer ID and PIN; do not register again.',
                ),
                const SizedBox(height: 22),
                if (registering) ...[
                  TextFormField(
                    controller: nameController,
                    autofillHints: const [AutofillHints.name],
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(
                      labelText: 'Full name',
                      prefixIcon: Icon(Icons.person_rounded),
                    ),
                    validator: _requiredValidator,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: mobileController,
                    autofillHints: const [AutofillHints.telephoneNumber],
                    keyboardType: TextInputType.phone,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(
                      labelText: 'Mobile number',
                      prefixIcon: Icon(Icons.phone_rounded),
                    ),
                    validator: _mobileValidator,
                  ),
                  const SizedBox(height: 12),
                ],
                if (!registering) ...[
                  TextFormField(
                    controller: customerIdController,
                    keyboardType: TextInputType.number,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    autofillHints: const [AutofillHints.username],
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(
                      labelText: 'Customer ID',
                      prefixIcon: Icon(Icons.badge_rounded),
                    ),
                    validator: _requiredValidator,
                  ),
                  const SizedBox(height: 12),
                ],
                TextFormField(
                  controller: pinController,
                  obscureText: true,
                  maxLength: 4,
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: const InputDecoration(
                    labelText: '4-digit PIN',
                    prefixIcon: Icon(Icons.pin_rounded),
                    counterText: '',
                  ),
                  validator: _pinValidator,
                  onFieldSubmitted: (_) => onSubmit(),
                ),
                const SizedBox(height: 20),
                PrimaryButton(
                  expanded: true,
                  label: submitting
                      ? 'Please wait...'
                      : registering
                      ? 'Create Account and Enroll'
                      : 'Continue to Verification',
                  icon: submitting
                      ? Icons.hourglass_top_rounded
                      : registering
                      ? Icons.person_add_alt_1_rounded
                      : Icons.login_rounded,
                  onPressed: submitting ? null : onSubmit,
                ),
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(registering ? 'Already registered?' : 'New customer?'),
                    TextButton(
                      onPressed: submitting
                          ? null
                          : () => context.goNamed(
                              registering
                                  ? RouteNames.login
                                  : RouteNames.register,
                            ),
                      child: Text(registering ? 'Login' : 'Register'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  static String? _requiredValidator(String? value) {
    return value == null || value.trim().isEmpty
        ? 'This field is required'
        : null;
  }

  static String? _pinValidator(String? value) {
    final pin = value ?? '';
    return !RegExp(r'^[0-9]{4}$').hasMatch(pin) ? 'Enter a 4-digit PIN' : null;
  }

  static String? _mobileValidator(String? value) {
    final mobile = value?.trim() ?? '';
    return mobile.length < 10 || int.tryParse(mobile) == null
        ? 'Enter a valid mobile number'
        : null;
  }
}
