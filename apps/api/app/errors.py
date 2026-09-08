class GeminiError(Exception):
    status_code = 502
    error_code = "gemini_error"
    public_message = "Gemini could not complete the request"

    def detail(self) -> dict[str, object]:
        return {
            "code": self.error_code,
            "message": self.public_message,
        }


class GeminiConfigurationError(GeminiError):
    status_code = 503
    error_code = "gemini_not_configured"
    public_message = "Gemini is not configured"


class GeminiSafetyError(GeminiError):
    status_code = 422
    error_code = "gemini_safety_blocked"
    public_message = "Gemini blocked this request for safety reasons"


class GeminiRequestError(GeminiError):
    def __init__(self, *, error_code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.error_code = error_code
        self.public_message = public_message


class GeminiUnavailableError(GeminiError):
    status_code = 503
    error_code = "gemini_unavailable"
    public_message = "No compatible Gemini model is currently available"

    def __init__(self, attempted_models: list[str]) -> None:
        super().__init__(self.public_message)
        self.attempted_models = attempted_models

    def detail(self) -> dict[str, object]:
        return {
            **super().detail(),
            "attempted_models": self.attempted_models,
        }


class GeminiStreamInterruptedError(GeminiError):
    error_code = "gemini_stream_interrupted"
    public_message = "The Gemini response was interrupted"
