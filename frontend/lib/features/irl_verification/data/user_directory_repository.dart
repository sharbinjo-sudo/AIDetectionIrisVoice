import 'package:dio/dio.dart';

import '../../../core/config/api_endpoints.dart';
import '../../../core/errors/error_mapper.dart';
import '../../../shared/models/biometric_user.dart';

class UserDirectoryRepository {
  UserDirectoryRepository(this._dio);

  final Dio _dio;

  Future<List<BiometricUser>> fetchUsers([String? query]) async {
    try {
      final response = await _dio.get<dynamic>(
        ApiEndpoints.users,
        queryParameters: query == null || query.isEmpty
            ? null
            : {'search': query},
      );
      final payload = response.data is Map<String, dynamic>
          ? response.data as Map<String, dynamic>
          : <String, dynamic>{};
      final rawList =
          payload['data']?['results'] ??
          payload['data'] ??
          payload['results'] ??
          payload;

      if (rawList is List) {
        return rawList
            .whereType<Map>()
            .map((item) => BiometricUser.fromJson(item.cast<String, dynamic>()))
            .toList();
      }
      return const [];
    } catch (error) {
      throw ErrorMapper.map(error);
    }
  }

  Future<String> fetchEnrollmentStatus(String userId) async {
    try {
      final response = await _dio.get<dynamic>(
        ApiEndpoints.enrollmentStatus(userId),
      );
      final payload = response.data is Map<String, dynamic>
          ? response.data as Map<String, dynamic>
          : <String, dynamic>{};
      final data =
          (payload['data'] as Map?)?.cast<String, dynamic>() ?? payload;
      return data['enrollment_status']?.toString() ?? 'UNKNOWN';
    } catch (error) {
      throw ErrorMapper.map(error);
    }
  }
}
