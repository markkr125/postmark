"""Convenient re-exports of the two model classes.

Usage::

    from database.models import CollectionModel, RequestModel
"""

from .collections.model.collection_model import CollectionModel
from .collections.model.request_model import RequestModel

__all__ = ["CollectionModel", "RequestModel"]
