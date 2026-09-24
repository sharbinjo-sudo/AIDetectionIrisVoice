import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/networking/dio_client.dart';
import '../../../shared/models/biometric_user.dart';
import '../data/user_directory_repository.dart';

final userDirectoryRepositoryProvider = Provider<UserDirectoryRepository>(
  (ref) => UserDirectoryRepository(ref.watch(dioProvider)),
);

class UserSearchState {
  const UserSearchState({
    required this.query,
    required this.users,
    required this.isLoading,
    this.error,
  });

  final String query;
  final List<BiometricUser> users;
  final bool isLoading;
  final String? error;

  factory UserSearchState.initial() =>
      const UserSearchState(query: '', users: [], isLoading: false);

  UserSearchState copyWith({
    String? query,
    List<BiometricUser>? users,
    bool? isLoading,
    String? error,
  }) {
    return UserSearchState(
      query: query ?? this.query,
      users: users ?? this.users,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

class UserSearchController extends Notifier<UserSearchState> {
  @override
  UserSearchState build() {
    Future<void>.microtask(loadUsers);
    return UserSearchState.initial();
  }

  Future<void> loadUsers([String query = '']) async {
    state = state.copyWith(query: query, isLoading: true, error: null);
    try {
      final users = await ref
          .read(userDirectoryRepositoryProvider)
          .fetchUsers(query);
      state = state.copyWith(users: users, isLoading: false, error: null);
    } catch (error) {
      state = state.copyWith(isLoading: false, error: error.toString());
    }
  }
}

final userSearchProvider =
    NotifierProvider<UserSearchController, UserSearchState>(
      UserSearchController.new,
    );
