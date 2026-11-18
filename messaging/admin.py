from django.contrib import admin

from .models import Consultation, Doctor, Message, Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("id", "external_id", "display_name", "created_at")
    search_fields = ("external_id", "display_name")
    readonly_fields = ("created_at",)


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "user")
    search_fields = ("display_name", "user__username", "user__email")


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "doctor", "created_at")
    list_select_related = ("patient", "doctor")
    list_filter = ("created_at",)
    search_fields = ("patient__external_id", "doctor__display_name")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "consultation",
        "sender_type",
        "external_message_id",
        "created_at",
    )
    list_select_related = ("consultation",)
    list_filter = ("sender_type", "created_at")
    search_fields = ("content", "external_message_id")
    readonly_fields = ("created_at",)
