enum ViewStatus {
  initial,
  loading,
  success,
  empty,
  validationError,
  networkError,
  serverError,
}

class ViewState<T> {
  const ViewState({required this.status, this.data, this.message});

  final ViewStatus status;
  final T? data;
  final String? message;

  bool get isLoading => status == ViewStatus.loading;

  factory ViewState.initial([T? data]) =>
      ViewState(status: ViewStatus.initial, data: data);
  factory ViewState.loading([T? data]) =>
      ViewState(status: ViewStatus.loading, data: data);
  factory ViewState.success(T data) =>
      ViewState(status: ViewStatus.success, data: data);
  factory ViewState.empty([String? message]) =>
      ViewState(status: ViewStatus.empty, message: message);
  factory ViewState.validationError(String message, [T? data]) => ViewState(
    status: ViewStatus.validationError,
    message: message,
    data: data,
  );
  factory ViewState.networkError(String message, [T? data]) =>
      ViewState(status: ViewStatus.networkError, message: message, data: data);
  factory ViewState.serverError(String message, [T? data]) =>
      ViewState(status: ViewStatus.serverError, message: message, data: data);
}
