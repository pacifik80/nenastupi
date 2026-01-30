class KadClient:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    async def search(self, query: str):
        # SOAP integration is complex; return empty if not OGRN/INN
        return []
