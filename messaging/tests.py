from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Consultation, Doctor, Message, Patient


User = get_user_model()


@override_settings(WEBHOOK_SECRET="test-webhook-secret")
class IncomingWebhookTests(APITestCase):
    def setUp(self):
        self.patient = Patient.objects.create(
            external_id="synthetic-patient-001",
            display_name="Test Patient",
        )
        self.doctor_user = User.objects.create_user(
            username="assigned-doctor",
            password="test-password-123",
        )
        self.doctor = Doctor.objects.create(
            user=self.doctor_user,
            display_name="Dr Assigned",
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
        )
        self.url = "/api/webhooks/messages/"
        self.payload = {
            "external_event_id": "event-test-001",
            "patient_identifier": self.patient.external_id,
            "consultation_id": self.consultation.pk,
            "message_text": "I have a question about my appointment.",
        }

    def post_webhook(self, payload=None, secret="test-webhook-secret"):
        headers = {}
        if secret is not None:
            headers["HTTP_X_WEBHOOK_SECRET"] = secret
        return self.client.post(
            self.url,
            payload if payload is not None else self.payload,
            format="json",
            **headers,
        )

    def test_valid_incoming_message_is_created(self):
        response = self.post_webhook()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["duplicate"])
        self.assertEqual(Message.objects.count(), 1)
        message = Message.objects.get()
        self.assertEqual(message.sender_type, Message.SenderType.PATIENT)
        self.assertEqual(message.external_message_id, "event-test-001")
        self.assertEqual(message.consultation, self.consultation)

    def test_missing_webhook_secret_is_rejected(self):
        response = self.post_webhook(secret=None)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Message.objects.count(), 0)

    def test_invalid_webhook_secret_is_rejected(self):
        response = self.post_webhook(secret="not-the-secret")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Message.objects.count(), 0)

    def test_unconfigured_webhook_secret_fails_closed(self):
        with override_settings(WEBHOOK_SECRET=""):
            response = self.post_webhook()

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(Message.objects.count(), 0)

    def test_invalid_payload_is_rejected(self):
        invalid_payload = {
            "external_event_id": "event-test-invalid",
            "patient_identifier": self.patient.external_id,
            "consultation_id": self.consultation.pk,
        }
        response = self.post_webhook(payload=invalid_payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Message.objects.count(), 0)

    def test_patient_cannot_be_attached_to_another_patients_consultation(self):
        other_patient = Patient.objects.create(external_id="synthetic-patient-002")
        payload = {
            **self.payload,
            "external_event_id": "event-cross-patient",
            "patient_identifier": other_patient.external_id,
        }

        response = self.post_webhook(payload=payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("consultation_id", response.data)
        self.assertEqual(Message.objects.count(), 0)

    def test_duplicate_event_is_idempotent(self):
        first = self.post_webhook()
        second = self.post_webhook()

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(second.data["duplicate"])
        self.assertEqual(first.data["message"]["id"], second.data["message"]["id"])
        self.assertEqual(Message.objects.count(), 1)

    def test_reused_event_id_with_different_payload_returns_conflict(self):
        self.post_webhook()
        changed_payload = {
            **self.payload,
            "message_text": "A different message using the same event ID.",
        }

        response = self.post_webhook(payload=changed_payload)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Message.objects.count(), 1)


class ConsultationMessagingTests(APITestCase):
    def setUp(self):
        self.patient = Patient.objects.create(
            external_id="synthetic-patient-100",
            display_name="Sample Patient",
        )
        self.assigned_user = User.objects.create_user(
            username="doctor-one",
            password="test-password-123",
        )
        self.assigned_doctor = Doctor.objects.create(
            user=self.assigned_user,
            display_name="Dr One",
        )
        self.other_user = User.objects.create_user(
            username="doctor-two",
            password="test-password-123",
        )
        self.other_doctor = Doctor.objects.create(
            user=self.other_user,
            display_name="Dr Two",
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.assigned_doctor,
        )

    def test_assigned_doctor_can_reply(self):
        self.client.force_authenticate(user=self.assigned_user)

        response = self.client.post(
            f"/api/consultations/{self.consultation.pk}/reply/",
            {"content": "Please describe when the symptoms began."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Message.objects.count(), 1)
        message = Message.objects.get()
        self.assertEqual(message.sender_type, Message.SenderType.DOCTOR)
        self.assertIsNone(message.external_message_id)

    def test_unassigned_doctor_cannot_reply(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(
            f"/api/consultations/{self.consultation.pk}/reply/",
            {"content": "This reply must be denied."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Message.objects.count(), 0)

    def test_assigned_doctor_can_read_chronological_history(self):
        patient_message = Message.objects.create(
            consultation=self.consultation,
            sender_type=Message.SenderType.PATIENT,
            content="My first message.",
            external_message_id="history-event-001",
        )
        doctor_message = Message.objects.create(
            consultation=self.consultation,
            sender_type=Message.SenderType.DOCTOR,
            content="My reply.",
        )
        self.client.force_authenticate(user=self.assigned_user)

        response = self.client.get(
            f"/api/consultations/{self.consultation.pk}/messages/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data["messages"]],
            [patient_message.pk, doctor_message.pk],
        )
        self.assertEqual(
            [item["sender_type"] for item in response.data["messages"]],
            ["patient", "doctor"],
        )

    def test_unassigned_doctor_cannot_read_history(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(
            f"/api/consultations/{self.consultation.pk}/messages/"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_user_without_doctor_profile_is_denied(self):
        ordinary_user = User.objects.create_user(
            username="ordinary-user",
            password="test-password-123",
        )
        self.client.force_authenticate(user=ordinary_user)

        response = self.client.get(
            f"/api/consultations/{self.consultation.pk}/messages/"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_user_cannot_read_history(self):
        response = self.client.get(
            f"/api/consultations/{self.consultation.pk}/messages/"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
