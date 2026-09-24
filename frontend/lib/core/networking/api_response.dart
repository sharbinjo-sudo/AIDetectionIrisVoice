class ApiResponse<T> {
  const ApiResponse({required this.success, required this.data, this.message});

  final bool success;
  final T data;
  final String? message;

  factory ApiResponse.fromJson(
    Map<String, dynamic> json,
    T Function(dynamic payload) decoder,
  ) {
    return ApiResponse(
      success: json['success'] != false,
      data: decoder(json['data'] ?? json),
      message: json['message']?.toString(),
    );
  }
}
