import hmac

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Consultation, Message
from .permissions import IsAssignedDoctor
from .serializers import (
    DoctorReplySerializer,
    IncomingMessageSerializer,
    MessageSerializer,
)
from .services import IdempotencyConflict, receive_patient_message


class IncomingMessageWebhookView(APIView):
    """Accept a simulated provider webhook authenticated by a shared test secret."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        expected_secret = settings.WEBHOOK_SECRET
        if not expected_secret:
            return Response(
                {"detail": "Webhook secret is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        supplied_secret = request.headers.get("X-Webhook-Secret", "")
        if not supplied_secret or not hmac.compare_digest(
            supplied_secret, expected_secret
        ):
            return Response(
                {"detail": "Missing or invalid webhook secret."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = IncomingMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            message, created = receive_patient_message(
                external_event_id=data["external_event_id"],
                consultation=data["consultation"],
                content=data["message_text"],
            )
        except IdempotencyConflict as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {
                "message": MessageSerializer(message).data,
                "duplicate": not created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class AssignedConsultationAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAssignedDoctor]

    def get_consultation(self, request, consultation_id):
        consultation = get_object_or_404(
            Consultation.objects.select_related("doctor"),
            pk=consultation_id,
        )
        self.check_object_permissions(request, consultation)
        return consultation


class DoctorReplyView(AssignedConsultationAPIView):
    def post(self, request, consultation_id):
        consultation = self.get_consultation(request, consultation_id)

        serializer = DoctorReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = Message.objects.create(
            consultation=consultation,
            sender_type=Message.SenderType.DOCTOR,
            content=serializer.validated_data["content"],
        )
        return Response(
            MessageSerializer(message).data,
            status=status.HTTP_201_CREATED,
        )


class ConsultationMessagesView(AssignedConsultationAPIView):
    def get(self, request, consultation_id):
        consultation = self.get_consultation(request, consultation_id)
        messages = consultation.messages.order_by("created_at", "id")
        return Response(
            {
                "consultation_id": consultation.pk,
                "messages": MessageSerializer(messages, many=True).data,
            }
        )
