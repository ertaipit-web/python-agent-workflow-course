class IntegrationError(Exception):
    pass


class AuthenticationError(IntegrationError):
    pass


class PermissionDeniedError(IntegrationError):
    pass


class NotFoundError(IntegrationError):
    pass


class ValidationRejectedError(IntegrationError):
    pass


class ServerError(IntegrationError):
    def __init__(self, message: str, *, attempts: int) -> None:
        super().__init__(message)
        self.attempts = attempts


class TransportTimeoutError(IntegrationError):
    pass


class WriteOutcomeUnknownError(IntegrationError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.effect_may_have_applied = True