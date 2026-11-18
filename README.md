# Caretekk Patient Messaging API

A small, self-contained Django REST Framework assessment project. It simulates an incoming patient message webhook and allows only the doctor assigned to a consultation to reply to and read its message history.

This is a synthetic assessment implementation. It does not connect to WhatsApp, use real provider credentials, or contain real patient information.

## Features

- Patient, doctor, consultation, and message data models.
- Shared-secret verification for the simulated incoming webhook.
- Consultation/patient relationship validation before a message is stored.
- Database-enforced uniqueness for incoming external event IDs.
- Idempotent webhook retries: an identical replay returns the original message; reuse of an event ID with a different payload returns HTTP 409.
- Token-authenticated doctor replies and consultation history.
- Object-level authorization for the assigned doctor.
- Automated tests for webhook security, validation, idempotency, reply permissions, and message history.

## Technology

- Python 3.13
- Django 6.1
- Django REST Framework
- SQLite for local development and tests
- uv for dependency and lock-file management

No Celery, Redis, Docker, PostgreSQL, frontend, or external WhatsApp integration is required.

## Setup

Install Python 3.13 and uv, then clone the repository:

~~~bash
git clone https://github.com/Rokari-19/caretekk-task.git
cd caretekk-task
git checkout feat/patient-messaging-api
uv sync --locked
~~~

Create a local environment file:

~~~bash
cp .env.example .env
~~~

Replace DJANGO_SECRET_KEY in .env with a locally generated random value. The WEBHOOK_SECRET in the example file is a dummy value for local testing only. The .env file is ignored by Git.

Apply migrations:

~~~bash
uv run --env-file .env python manage.py migrate
~~~

Create an admin account and start the server:

~~~bash
uv run --env-file .env python manage.py createsuperuser
uv run --env-file .env python manage.py runserver
~~~

The API is available at http://127.0.0.1:8000/ and the Django admin is at http://127.0.0.1:8000/admin/.

If you use pip rather than uv, install the dependencies in pyproject.toml and export the environment variables from .env before running manage.py. Do not commit .env.

## Environment variables

| Variable | Purpose | Local example |
|---|---|---|
| DJANGO_SECRET_KEY | Django signing key | Replace the placeholder with a random value |
| DEBUG | Enables Django debug mode | True |
| ALLOWED_HOSTS | Comma-separated allowed host names | 127.0.0.1,localhost |
| WEBHOOK_SECRET | Shared secret expected in X-Webhook-Secret | local-test-webhook-secret |

The webhook returns HTTP 503 when WEBHOOK_SECRET is not configured. This is intentional fail-closed behavior.

## Create sample users and a consultation

Create a doctor account, doctor profile, patient, and consultation using Django shell:

~~~bash
uv run --env-file .env python manage.py shell
~~~

~~~python
from django.contrib.auth import get_user_model
from messaging.models import Consultation, Doctor, Patient

User = get_user_model()

doctor_user = User.objects.create_user(
    username="doctor1",
    password="LocalOnly-Password-123",
)
doctor = Doctor.objects.create(
    user=doctor_user,
    display_name="Dr Example",
)

other_user = User.objects.create_user(
    username="doctor2",
    password="LocalOnly-Password-456",
)
other_doctor = Doctor.objects.create(
    user=other_user,
    display_name="Dr Other",
)

patient = Patient.objects.create(
    external_id="synthetic-patient-001",
    display_name="Sample Patient",
)
consultation = Consultation.objects.create(
    patient=patient,
    doctor=doctor,
)

print("Consultation ID:", consultation.pk)
~~~

The second doctor is deliberately not assigned to this consultation. Use that account to demonstrate a denied request. These records are synthetic and should remain local.

## API endpoints

### 1. Incoming patient message

**POST /api/webhooks/messages/**

Required header:

**X-Webhook-Secret: WEBHOOK_SECRET**

Example request:

~~~bash
curl -X POST http://127.0.0.1:8000/api/webhooks/messages/ \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: local-test-webhook-secret" \
  -d '{
    "external_event_id": "event-demo-001",
    "patient_identifier": "synthetic-patient-001",
    "consultation_id": 1,
    "message_text": "I have a question about my appointment."
  }'
~~~

The consultation ID must belong to the supplied patient. An invalid or mismatched relationship is rejected with HTTP 400.

Responses:

- HTTP 201: a new message was stored.
- HTTP 200: the same event and payload were already processed; the original message is returned.
- HTTP 400: required fields, patient, consultation, or relationship validation failed.
- HTTP 403: the webhook secret is missing or invalid.
- HTTP 409: the event ID was previously used with a different payload.
- HTTP 503: WEBHOOK_SECRET is not configured.

### 2. Obtain a doctor API token

**POST /api/auth/token/**

~~~bash
curl -X POST http://127.0.0.1:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "doctor1", "password": "LocalOnly-Password-123"}'
~~~

The response contains a token. Store it in a shell variable for the next requests:

~~~bash
TOKEN="paste-token-value-here"
~~~

### 3. Reply to a consultation

**POST /api/consultations/{consultation_id}/reply/**

~~~bash
curl -X POST http://127.0.0.1:8000/api/consultations/1/reply/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token $TOKEN" \
  -d '{"content": "Please describe when the symptoms began."}'
~~~

A successful reply returns HTTP 201. An authenticated doctor who is not assigned to the consultation receives HTTP 403. Anonymous requests are rejected.

### 4. Read consultation message history

**GET /api/consultations/{consultation_id}/messages/**

~~~bash
curl http://127.0.0.1:8000/api/consultations/1/messages/ \
  -H "Authorization: Token $TOKEN"
~~~

Messages are returned in ascending creation-time order, with the message ID used as a stable tie-breaker. Only the assigned doctor can read the history.

## Run tests

Run the complete Django test suite:

~~~bash
uv run --env-file .env python manage.py test messaging
~~~

The tests use Django's isolated test database and synthetic records. No running server or external account is required.

## Data model and engineering decisions

- **Patient:** has a unique external identifier used by the simulated webhook.
- **Doctor:** a one-to-one profile for a Django authentication user. Authentication stays with Django; the profile represents the doctor's role.
- **Consultation:** links one patient to one assigned doctor.
- **Message:** belongs to one consultation and records sender type, content, and a server-generated timestamp. Incoming patient messages have a unique external message ID. Doctor replies have no provider event ID.

The central reliability decision is a unique database constraint on Message.external_message_id, combined with Django's get_or_create inside an atomic transaction. This is not an application-only existence check. Under concurrent submissions with the same event ID, the database uniqueness constraint permits one insert; the competing get_or_create call resolves to the existing row. The API then compares the stored consultation and content: an exact replay is acknowledged, while a conflicting replay returns HTTP 409.

SQLite is sufficient for this focused assessment and enforces the uniqueness constraint. SQLite serializes writes and may report lock contention under heavier concurrent write load. PostgreSQL would be the better production database for sustained concurrent traffic, but is intentionally not added just for this assessment.

Additional assumptions and tradeoffs:

- The event ID is globally unique for this single simulated webhook source. A multi-provider integration should include a provider/source field in the uniqueness key.
- A webhook must reference an existing patient and an existing consultation belonging to that patient. The webhook does not create patients or consultations.
- Patients do not authenticate in this assessment. Doctor reply and history endpoints require an authenticated Django user with a Doctor profile assigned to the consultation.
- The webhook uses a shared test secret in a request header, not a real WhatsApp signature scheme. A production integration would verify the provider's documented signature over the raw request body and add replay-window controls.
- Timestamps are generated by the server and stored in UTC.
- Token authentication is provided for the demo. Basic and session authentication are also enabled for local development and the browsable API; production deployments should use HTTPS.
- Message delivery, read receipts, attachments, rate limiting, audit retention, and outbound provider delivery are outside the assessment scope.

## AI assistance disclosure

AI assistance was used to draft portions of the implementation, tests, and developer documentation. The repository owner should review the code, run the test suite, and be prepared to explain the data model, authorization checks, unique constraint, transaction behavior, and stated limitations during a code walkthrough.
