import uuid


class IndexingService:
    @staticmethod
    def generate_index_version() -> str:
        return f"v_{uuid.uuid4().hex[:12]}"
