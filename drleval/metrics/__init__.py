"""Metrics — plugin registry. Importing this package registers all metrics."""
from . import hard as _hard  # noqa: F401
from . import soft as _soft  # noqa: F401
from .registry import METRICS, register  # noqa: F401
