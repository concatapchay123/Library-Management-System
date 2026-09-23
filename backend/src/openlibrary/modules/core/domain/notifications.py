"""Domain entities and business rules for in-app notifications."""

from __future__ import annotations

from enum import StrEnum


class NotificationStatus(StrEnum):
    """Lifecycle states of an in-app notification."""

    UNREAD = "unread"
    READ = "read"


class NotificationChannel(StrEnum):
    """Delivery channels for notifications."""

    IN_APP = "in_app"
    EMAIL = "email"


class NotificationError(Exception):
    """Base exception for notification domain errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        title: str = "Notification Error",
        problem_type: str = "https://openlibraryos.example/problems/notification-error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.title = title
        self.problem_type = problem_type


class NotificationNotFoundError(NotificationError):
    """Raised when a notification cannot be found for the tenant or user."""

    def __init__(self, message: str = "Notification not found") -> None:
        super().__init__(
            message,
            status_code=404,
            title="Notification Not Found",
            problem_type="https://openlibraryos.example/problems/notification-not-found",
        )


class InvalidNotificationStatusTransitionError(NotificationError):
    """Raised when an illegal status transition is requested."""

    def __init__(self, message: str = "Invalid notification status transition") -> None:
        super().__init__(
            message,
            status_code=409,
            title="Invalid Notification Status Transition",
            problem_type="https://openlibraryos.example/problems/invalid-notification-status-transition",
        )
