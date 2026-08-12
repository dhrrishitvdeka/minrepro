"""minrepro: structure-aware reduction of failing JSON/YAML configs."""

from minrepro.api import reduce_data, reduce_file
from minrepro.model import ReductionEvent, ReductionResult
from minrepro.oracle import (
    BaselineNotInteresting,
    Oracle,
    OracleConfig,
    OracleError,
    OracleResult,
)
from minrepro.parse import ParseError, dump, dumps, load, loads
from minrepro.report import line_count, removed_percent, utf8_size
from minrepro.shrink import Shrinker

__version__ = "0.2.1"

__all__ = [
    "BaselineNotInteresting",
    "Oracle",
    "OracleConfig",
    "OracleError",
    "OracleResult",
    "ParseError",
    "ReductionEvent",
    "ReductionResult",
    "Shrinker",
    "__version__",
    "dump",
    "dumps",
    "line_count",
    "load",
    "loads",
    "reduce_data",
    "reduce_file",
    "removed_percent",
    "utf8_size",
]
