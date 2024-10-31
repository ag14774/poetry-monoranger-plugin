"""Copyright (C) 2024 GlaxoSmithKline plc

This module defines the LockModifier class, which modifies the behavior of certain Poetry commands
(`lock`, `install`, `update`) to support monorepo setups. It ensures these commands behave as if they
were run from the monorepo root directory, maintaining a shared lockfile.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from poetry.config.config import Config
from poetry.console.commands.install import InstallCommand
from poetry.console.commands.lock import LockCommand
from poetry.console.commands.update import UpdateCommand
from poetry.factory import Factory
from poetry.installation.installer import Installer

if TYPE_CHECKING:
    from cleo.events.console_command_event import ConsoleCommandEvent

    from poetry_monoranger_plugin.config import MonorangerConfig


class LockModifier:
    """Modifies Poetry commands (`lock`, `install`, `update`) for monorepo support.

    Ensures these commands behave as if they were run from the monorepo root directory
    even when run from a subdirectory, thus maintaining a shared lockfile.
    """

    def __init__(self, plugin_conf: MonorangerConfig):
        self.plugin_conf = plugin_conf

    def execute(self, event: ConsoleCommandEvent):
        """Modifies the command to run from the monorepo root.

        Ensures the command is one of `LockCommand`, `InstallCommand`, or `UpdateCommand`.
        Sets up the necessary Poetry instance and installer for the monorepo root so that
        the command behaves as if it was executed from within the root directory.

        Args:
            event (ConsoleCommandEvent): The triggering event.
        """
        command = event.command
        assert isinstance(
            command, (LockCommand, InstallCommand, UpdateCommand)
        ), f"{self.__class__.__name__} can only be used for `poetry lock`, `poetry install`, and `poetry update` commands"

        io = event.io
        io.write_line("<info>Running command from monorepo root directory</info>")

        # Force reload global config in order to undo changes that happened due to subproject's poetry.toml configs
        _ = Config.create(reload=True)
        monorepo_root = (command.poetry.pyproject_path.parent / self.plugin_conf.monorepo_root).resolve()
        monorepo_root_poetry = Factory().create_poetry(
            cwd=monorepo_root, io=io, disable_cache=command.poetry.disable_cache
        )

        installer = Installer(
            io,
            command.env,
            monorepo_root_poetry.package,
            monorepo_root_poetry.locker,
            monorepo_root_poetry.pool,
            monorepo_root_poetry.config,
            disable_cache=monorepo_root_poetry.disable_cache,
        )

        command.set_poetry(monorepo_root_poetry)
        command.set_installer(installer)
