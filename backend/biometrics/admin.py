from django.contrib import admin

from .models import AuthenticationAttempt, BiometricUser


@admin.register(BiometricUser)
class BiometricUserAdmin(admin.ModelAdmin):
    list_display = (
        "external_id",
        "full_name",
        "enrollment_status",
        "enrolled_eye_side",
        "last_enrolled_at",
    )
    list_filter = ("enrollment_status", "enrolled_eye_side")
    search_fields = ("external_id", "full_name")


@admin.register(AuthenticationAttempt)
class AuthenticationAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "decision",
        "fusion_score",
        "saved",
        "created_at",
    )
    list_filter = ("decision", "saved")
    search_fields = ("user__external_id", "user__full_name")
