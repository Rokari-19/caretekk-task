from rest_framework.permissions import BasePermission


class IsAssignedDoctor(BasePermission):
    message = "Only the doctor assigned to this consultation may access its messages."

    def has_object_permission(self, request, view, consultation):
        return (
            request.user.is_authenticated
            and request.user.is_active
            and consultation.doctor.user_id == request.user.pk
        )
