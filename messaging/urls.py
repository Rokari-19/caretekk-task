from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

from .views import (
    ConsultationMessagesView,
    DoctorReplyView,
    IncomingMessageWebhookView,
)

urlpatterns = [
    path("auth/token/", obtain_auth_token, name="obtain-auth-token"),
    path(
        "webhooks/messages/",
        IncomingMessageWebhookView.as_view(),
        name="incoming-message-webhook",
    ),
    path(
        "consultations/<int:consultation_id>/reply/",
        DoctorReplyView.as_view(),
        name="consultation-reply",
    ),
    path(
        "consultations/<int:consultation_id>/messages/",
        ConsultationMessagesView.as_view(),
        name="consultation-messages",
    ),
]
