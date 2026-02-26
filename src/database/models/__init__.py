"""
Convenient re-exports of the two tables.
Import like:  from src.models import Collection, Request
"""

from .collections.model.collection_model import CollectionModel
from .collections.model.request_model import RequestModel

__all__ = ["CollectionModel", "RequestModel"]
