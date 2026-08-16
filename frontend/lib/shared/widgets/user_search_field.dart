import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/irl_verification/providers/user_search_provider.dart';
import '../models/biometric_user.dart';

class UserSearchField extends ConsumerStatefulWidget {
  const UserSearchField({
    super.key,
    required this.onSelected,
    this.selectedUser,
  });

  final ValueChanged<BiometricUser?> onSelected;
  final BiometricUser? selectedUser;

  @override
  ConsumerState<UserSearchField> createState() => _UserSearchFieldState();
}

class _UserSearchFieldState extends ConsumerState<UserSearchField> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(userSearchProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          controller: _controller,
          decoration: const InputDecoration(
            labelText: 'Search registered user',
            hintText: 'Enter name or user ID',
          ),
          onChanged: (value) =>
              ref.read(userSearchProvider.notifier).loadUsers(value),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<BiometricUser>(
          initialValue: widget.selectedUser,
          items: state.users
              .map(
                (user) => DropdownMenuItem<BiometricUser>(
                  value: user,
                  child: Text('${user.fullName} (${user.externalId})'),
                ),
              )
              .toList(),
          onChanged: widget.onSelected,
          decoration: const InputDecoration(labelText: 'Selected user'),
        ),
      ],
    );
  }
}
