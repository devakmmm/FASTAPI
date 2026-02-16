from fastapi import HTTPException


class AppException(Exception):
    """Base exception for application errors."""
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    
    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppException):
    """Resource not found."""
    status_code = 404
    error_code = "NOT_FOUND"


class ConflictError(AppException):
    """Resource conflict (duplicate, etc)."""
    status_code = 409
    error_code = "CONFLICT"


class ValidationError(AppException):
    """Business validation failed."""
    status_code = 400
    error_code = "VALIDATION_ERROR"


class AuthenticationError(AppException):
    """Authentication failed."""
    status_code = 401
    error_code = "AUTHENTICATION_ERROR"


class AuthorizationError(AppException):
    """Authorization failed."""
    status_code = 403
    error_code = "AUTHORIZATION_ERROR"
