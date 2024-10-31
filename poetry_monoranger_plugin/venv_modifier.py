"""Copyright (C) 2024 GlaxoSmithKline plc

This module contains the VenvModifier class, which modifies the virtual environment (venv) for a Poetry
command. It ensures that the shared virtual environment of the monorepo root is activated for
commands that require an environment such as `poetry shell` and `poetry run`.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from poetry.config.config import Config
from poetry.console.commands.env_command import EnvCommand
from poetry.console.commands.installer_command import InstallerCommand
from poetry.console.commands.self.self_command import SelfCommand
from poetry.factory import Factory
from poetry.installation.installer import Installer
from poetry.utils.env import EnvManager

if TYPE_CHECKING:
    from cleo.events.console_command_event import ConsoleCommandEvent

    from poetry_monoranger_plugin.config import MonorangerConfig


class VenvModifier:
    """A class to modify the virtual environment (venv) of poetry commands.

    This class ensures that the appropriate virtual environment is activated for commands that require an environment.
    It prevents the activation of the per-project environments and forces the activation of the monorepo root venv.
    If another venv is already activated, it does not activate any other venv to maintain consistency with Poetry's
    behavior.
    """

    def __init__(self, plugin_conf: MonorangerConfig):
        self.plugin_conf: MonorangerConfig = plugin_conf

    def execute(self, event: ConsoleCommandEvent):
        """Executes the necessary modifications so that the poetry command uses the monorepo root venv.

        This method ensures that the appropriate virtual environment is activated for commands that require an environment.
        For commands that require an installer, it updates the installer to use the monorepo root venv.

        Args:
            event (ConsoleCommandEvent): The triggering event.
        """
        command = event.command
        assert isinstance(command, EnvCommand) and not isinstance(
            command, SelfCommand
        ), f"{self.__class__.__name__} can only be used for commands that require an environment (except `poetry self`)"

        # We don't want to activate the monorepo root venv if we are already inside a venv
        # in order to be consistent with poetry's current behavior.
        # Check if we are inside a virtualenv or not
        # Conda sets CONDA_PREFIX in its envs, see
        # https://github.com/conda/conda/issues/2764
        env_prefix = os.environ.get("VIRTUAL_ENV", os.environ.get("CONDA_PREFIX"))
        conda_env_name = os.environ.get("CONDA_DEFAULT_ENV")
        # It's probably not a good idea to pollute Conda's global "base" env, since
        # most users have it activated all the time.
        in_venv = env_prefix is not None and conda_env_name != "base"
        if in_venv:
            return

        io = event.io
        poetry = command.poetry

        # Force reload global config in order to undo changes that happened due to subproject's poetry.toml configs
        _ = Config.create(reload=True)
        monorepo_root = (poetry.pyproject_path.parent / self.plugin_conf.monorepo_root).resolve()
        monorepo_root_poetry = Factory().create_poetry(cwd=monorepo_root, io=io, disable_cache=poetry.disable_cache)

        io.write_line(f"<info>Using monorepo root venv <fg=green>{monorepo_root.name}</></info>\n")
        env_manager = EnvManager(monorepo_root_poetry, io=io)
        root_env = env_manager.create_venv()
        command.set_env(root_env)

        if not isinstance(command, InstallerCommand):
            return

        # Update installer for commands that require an installer
        installer = Installer(
            io,
            root_env,
            command.poetry.package,
            command.poetry.locker,
            command.poetry.pool,
            command.poetry.config,
            disable_cache=command.poetry.disable_cache,
        )
        command.set_installer(installer)
