class BiometricServiceError(Exception):
    status_code = 400


class BiometricValidationError(BiometricServiceError):
    status_code = 400


class BiometricProcessingError(BiometricServiceError):
    status_code = 422


class ModelUnavailableError(BiometricServiceError):
    status_code = 503


class EnrollmentIncompleteError(BiometricServiceError):
    status_code = 409
