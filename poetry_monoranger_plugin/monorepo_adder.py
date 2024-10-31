"""Copyright (C) 2024 GlaxoSmithKline plc

This module defines classes and methods to modify the behavior of Poetry's add and remove commands for monorepo support.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from poetry.config.config import Config
from poetry.console.commands.add import AddCommand
from poetry.console.commands.remove import RemoveCommand
from poetry.factory import Factory
from poetry.installation.installer import Installer
from poetry.poetry import Poetry
from tomlkit.toml_document import TOMLDocument

if TYPE_CHECKING:
    from cleo.events.console_command_event import ConsoleCommandEvent
    from cleo.events.console_terminate_event import ConsoleTerminateEvent

    from poetry_monoranger_plugin.config import MonorangerConfig


class DummyInstaller(Installer):
    """A dummy installer that overrides the run method and disables it

    Note: For more details, refer to the docstring of `MonorepoAdderRemover`.
    """

    @classmethod
    def from_installer(cls, installer: Installer):
        """Creates a DummyInstaller instance from an existing Installer instance.

        Args:
            installer (Installer): The original installer instance.

        Returns:
            DummyInstaller: A new DummyInstaller instance with the same attributes.
        """
        new_installer = cls.__new__(cls)
        new_installer.__dict__.update(installer.__dict__)
        return new_installer

    def run(self):
        """Overrides the run method to always return 0. The add/remove commands will modify
        the pyproject.toml file only if this command returns 0.

        Returns:
            int: Always returns 0.
        """
        return 0


class MonorepoAdderRemover:
    """A class to modify the behavior of Poetry's add and remove commands for monorepo support.

    This class ensures that the add and remove commands are executed in a way that supports
    monorepo setups, including handling the shared lock file and rolling back changes if needed.

    Under normal circumstances, the add/remove commands modify the per-project lockfile, and if it
    was modified successfully, *only then* the pyproject.toml file is updated. This leaves the
    pyproject.toml in a good state in case the lockfile generation/dependency resolution fails.

    However, in a monorepo setup, we want to maintain a single lockfile for all the projects in the
    monorepo. This means that the add/remove commands should not generate a per-project lockfile.The
    purpose of the DummyInstaller is to disable the installation part of the add/remove commands
    and just allow the add/remove to directly modify the pyproject.toml file without generating a
    per-project lockfile.

    After the pyproject.toml file is modified, we can update the root lockfile by creating a new
    Installer and executing the steps that are normally executed by the add/remove command. Since
    with this approach the pyproject.toml file is modified before lockfile updating, we need to
    ensure that the changes are rolled back in case of an error during the lockfile update.

    """

    def __init__(self, plugin_conf: MonorangerConfig):
        self.plugin_conf = plugin_conf
        self.pre_add_pyproject: None | TOMLDocument = None

    def execute(self, event: ConsoleCommandEvent):
        """Replaces the installer with a dummy installer to disable the installation part of the add/remove commands.

        This method creates a copy of the poetry object to prevent the command from modifying the original
        poetry object and sets a dummy installer to disable the installation part of the add/remove commands.
        It allows the add/remove to only modify the pyproject.toml file without generating a per-project lockfile.

        Args:
            event (ConsoleCommandEvent): The event that triggered the command.
        """
        command = event.command
        assert isinstance(
            command, (AddCommand, RemoveCommand)
        ), f"{self.__class__.__name__} can only be used for `poetry add` and `poetry remove` command"

        # Create a copy of the poetry object to prevent the command from modifying the original poetry object
        poetry = Poetry.__new__(Poetry)
        poetry.__dict__.update(command.poetry.__dict__)
        command.set_poetry(poetry)

        self.pre_add_pyproject = copy.deepcopy(poetry.file.read())

        installer = DummyInstaller.from_installer(command.installer)
        command.set_installer(installer)

    def post_execute(self, event: ConsoleTerminateEvent):
        """Handles the post-execution steps for the add or remove command, including rolling back changes if needed.

        This method updates the root lockfile by creating a new Installer and executing the steps that are normally
        executed by the add/remove command. If an error occurs during the lockfile update, it rolls back the changes
        to the pyproject.toml file.

        Args:
            event (ConsoleTerminateEvent): The event that triggered the command termination.
        """
        command = event.command
        assert isinstance(
            command, (AddCommand, RemoveCommand)
        ), f"{self.__class__.__name__} can only be used for `poetry add` and `poetry remove` command"

        io = event.io
        poetry = command.poetry

        if self.pre_add_pyproject and (poetry.file.read() == self.pre_add_pyproject):
            return

        # Force reload global config in order to undo changes that happened due to subproject's poetry.toml configs
        _ = Config.create(reload=True)
        monorepo_root = (poetry.pyproject_path.parent / self.plugin_conf.monorepo_root).resolve()
        monorepo_root_poetry = Factory().create_poetry(cwd=monorepo_root, io=io, disable_cache=poetry.disable_cache)

        installer = Installer(
            io,
            command.env,
            monorepo_root_poetry.package,
            monorepo_root_poetry.locker,
            monorepo_root_poetry.pool,
            monorepo_root_poetry.config,
            disable_cache=monorepo_root_poetry.disable_cache,
        )

        installer.dry_run(command.option("dry-run"))
        installer.verbose(io.is_verbose())
        installer.update(True)
        installer.execute_operations(not command.option("lock"))

        installer.whitelist([poetry.package.name])

        last_exc = None
        status = 0

        try:
            status = installer.run()
        except Exception as e:
            last_exc = e
            status = 1
        finally:
            if status != 0 and not command.option("dry-run") and self.pre_add_pyproject is not None:
                io.write_line("\n<error>An error occurred during the installation. Rolling back changes...</error>")
                assert isinstance(self.pre_add_pyproject, TOMLDocument)
                poetry.file.write(self.pre_add_pyproject)

            if last_exc is not None:
                raise last_exc

            event.set_exit_code(status)
