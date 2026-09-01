import pytest
from uuid import uuid4
from app.modules.knowledge.application.indexing_service import IndexingService


def test_indexing_service_version():
    version = IndexingService.generate_index_version()
    assert isinstance(version, str)
    assert len(version) > 0
