import 'package:dio/dio.dart';

import '../../../core/config/api_endpoints.dart';
import '../../../core/errors/error_mapper.dart';
import '../models/backend_health_status.dart';

class BackendHealthRepository {
  BackendHealthRepository(this._dio);

  final Dio _dio;

  Future<BackendHealthStatus> fetch() async {
    try {
      final response = await _dio.get<dynamic>(ApiEndpoints.health);
      final payload = response.data is Map<String, dynamic>
          ? response.data as Map<String, dynamic>
          : <String, dynamic>{};
      final data =
          (payload['data'] as Map?)?.cast<String, dynamic>() ?? payload;
      return BackendHealthStatus.fromJson(data);
    } catch (error) {
      throw ErrorMapper.map(error);
    }
  }
}
