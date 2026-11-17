from django.db import transaction

from .models import Message


class IdempotencyConflict(Exception):
    """Raised when an event ID is reused for a different message."""


@transaction.atomic
def receive_patient_message(*, external_event_id, consultation, content):
    """
    Persist one incoming event.

    get_or_create is safe here because external_message_id has a database-level
    unique constraint. If concurrent requests race to insert the same ID, the
    database permits one row and Django retrieves that row for the other request.
    """
    message, created = Message.objects.get_or_create(
        external_message_id=external_event_id,
        defaults={
            "consultation": consultation,
            "sender_type": Message.SenderType.PATIENT,
            "content": content,
        },
    )

    same_event_payload = (
        message.sender_type == Message.SenderType.PATIENT
        and message.consultation_id == consultation.pk
        and message.content == content
    )
    if not created and not same_event_payload:
        raise IdempotencyConflict(
            "This external event ID has already been used with a different payload."
        )

    return message, created
