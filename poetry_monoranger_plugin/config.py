"""Copyright (C) 2024 GlaxoSmithKline plc

This module defines the configuration class for the Monoranger plugin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class MonorangerConfig:
    """Configuration class for Monoranger.

    Attributes:
        enabled (bool): Flag to enable or disable Monoranger. Defaults to False.
        monorepo_root (str): Path to the root of the monorepo. Defaults to "../".
        version_rewrite_rule (Literal['==', '~', '^', '>=,<']): Rule for version rewriting. Defaults to "^".
    """

    enabled: bool = False
    monorepo_root: str = "../"
    version_rewrite_rule: Literal["==", "~", "^", ">=,<"] = "^"

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
