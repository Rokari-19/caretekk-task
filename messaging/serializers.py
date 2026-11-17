from rest_framework import serializers

from .models import Consultation, Message, Patient


class IncomingMessageSerializer(serializers.Serializer):
    external_event_id = serializers.CharField(max_length=255, trim_whitespace=True)
    patient_identifier = serializers.CharField(max_length=100, trim_whitespace=True)
    consultation_id = serializers.IntegerField(min_value=1)
    message_text = serializers.CharField(max_length=10_000, trim_whitespace=True)

    def validate(self, attrs):
        try:
            patient = Patient.objects.get(external_id=attrs["patient_identifier"])
        except Patient.DoesNotExist:
            raise serializers.ValidationError(
                {"patient_identifier": "No patient exists with this identifier."}
            )

        try:
            consultation = Consultation.objects.select_related("patient").get(
                pk=attrs["consultation_id"]
            )
        except Consultation.DoesNotExist:
            raise serializers.ValidationError(
                {"consultation_id": "Consultation does not exist."}
            )

        if consultation.patient_id != patient.pk:
            raise serializers.ValidationError(
                {
                    "consultation_id": (
                        "This consultation does not belong to the supplied patient."
                    )
                }
            )

        attrs["patient"] = patient
        attrs["consultation"] = consultation
        return attrs


class DoctorReplySerializer(serializers.Serializer):
    content = serializers.CharField(max_length=10_000, trim_whitespace=True)


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = (
            "id",
            "sender_type",
            "content",
            "created_at",
            "external_message_id",
        )
        read_only_fields = fields
