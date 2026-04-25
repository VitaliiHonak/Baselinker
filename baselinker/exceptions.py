class BaselinkerError(Exception):
    pass


class BaselinkerAPIError(BaselinkerError):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(f"[{error_code}] {message}")
