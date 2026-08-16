from django.urls import path

from .views import (
    AuthenticationAttemptSaveView,
    BiometricAuthenticateView,
    HealthView,
    IrisTestView,
    SystemConfigurationView,
    UserDetailView,
    UserEnrollmentStatusView,
    UserListView,
    VoiceTestView,
)


urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path(
        "system/configuration/",
        SystemConfigurationView.as_view(),
        name="system-configuration",
    ),
    path("users/", UserListView.as_view(), name="user-list"),
    path("users/<str:user_id>/", UserDetailView.as_view(), name="user-detail"),
    path(
        "users/<str:user_id>/enrollment/status/",
        UserEnrollmentStatusView.as_view(),
        name="user-enrollment-status",
    ),
    path("test/iris/", IrisTestView.as_view(), name="test-iris"),
    path("test/voice/", VoiceTestView.as_view(), name="test-voice"),
    path(
        "biometric-authenticate/",
        BiometricAuthenticateView.as_view(),
        name="biometric-authenticate",
    ),
    path(
        "authentication-attempts/<uuid:attempt_id>/save/",
        AuthenticationAttemptSaveView.as_view(),
        name="authentication-attempt-save",
    ),
]
