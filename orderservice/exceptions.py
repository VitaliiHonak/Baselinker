class OrderServiceError(Exception):
    pass


class OrderServiceAPIError(OrderServiceError):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {body}")
