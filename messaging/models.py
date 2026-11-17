from django.conf import settings
from django.db import models
from django.db.models import Q


class Patient(models.Model):
    """A synthetic patient record identified by an external system identifier."""

    external_id = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.display_name or self.external_id


class Doctor(models.Model):
    """Doctor profile linked to a Django account used for authentication."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="doctor_profile",
    )
    display_name = models.CharField(max_length=150, blank=True)

    def __str__(self):
        return self.display_name or self.user.get_username()


class Consultation(models.Model):
    """A patient consultation with exactly one assigned doctor."""

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="consultations",
    )
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.PROTECT,
        related_name="consultations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Consultation {self.pk} ({self.patient.external_id})"


class Message(models.Model):
    class SenderType(models.TextChoices):
        PATIENT = "patient", "Patient"
        DOCTOR = "doctor", "Doctor"

    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender_type = models.CharField(max_length=10, choices=SenderType.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    external_message_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text="Provider event ID for an incoming patient message; null for doctor replies.",
    )

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        sender_type=SenderType.PATIENT,
                        external_message_id__isnull=False,
                    )
                    | Q(
                        sender_type=SenderType.DOCTOR,
                        external_message_id__isnull=True,
                    )
                ),
                name="message_external_id_matches_sender",
            ),
        ]

    def __str__(self):
        return f"{self.sender_type}: {self.content[:40]}"
