"""anneal — iterative code-hardening via audit+fix or Red-vs-Blue adversarial loops."""

from __future__ import annotations

__version__ = "0.0.1"

from anneal.config import AnnealConfig
from anneal.result import AnnealResult
from anneal.loop_classic import anneal_classic
from anneal.loop_adversarial import anneal_adversarial

__all__ = [
    "__version__",
    "AnnealConfig",
    "AnnealResult",
    "anneal_classic",
    "anneal_adversarial",
]
