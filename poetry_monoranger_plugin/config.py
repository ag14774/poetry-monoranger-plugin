"""Copyright (C) 2024 GlaxoSmithKline plc

This module defines the configuration class for the Monoranger plugin.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class MonorangerConfig:
    """Configuration class for Monoranger.

    Attributes:
        enabled (bool): Flag to enable or disable Monoranger. Defaults to False.
        monorepo_root (str): Path to the root of the monorepo. Defaults to "../".
        version_pinning_rule (Literal['==', '~', '^', '>=,<']): Rule for pinning version of path dependencies. Defaults to "^".
    """

    enabled: bool = False
    monorepo_root: str = "../"
    version_pinning_rule: Literal["==", "~", "^", ">=,<"] = None  # type: ignore[assignment]
    version_rewrite_rule: Literal["==", "~", "^", ">=,<", None] = None

    def __post_init__(self):
        if self.version_pinning_rule is None and self.version_rewrite_rule is None:
            self.version_pinning_rule = "^"  # default value
        elif self.version_rewrite_rule is not None and self.version_pinning_rule is not None:
            raise ValueError(
                "Cannot specify both `version_pinning_rule` and `version_rewrite_rule`. "
                "`version_rewrite_rule` is deprecated. Please use version_pinning_rule instead."
            )
        elif self.version_rewrite_rule is not None:
            with warnings.catch_warnings():
                warnings.filterwarnings("default", category=DeprecationWarning)
                warnings.warn(
                    "`version_rewrite_rule` is deprecated. Please use `version_pinning_rule` instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            self.version_pinning_rule = self.version_rewrite_rule

    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        """Creates an instance of MonorangerConfig from a dictionary.

        Args:
            d (dict[str, Any]): Dictionary containing configuration values.

        Returns:
            MonorangerConfig: An instance of MonorangerConfig with values populated from the dictionary.
        """
        d = {k.replace("-", "_"): v for k, v in d.items()}
        return cls(**d)
