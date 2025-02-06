"""Copyright (C) 2024 GlaxoSmithKline plc

This module defines the ExportModifier class, which modifies the `poetry export` command. Similarly to
`poetry build` this exports the dependencies of a subproject to an alternative format while ensuring path
dependencies are pinned to specific versions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from poetry.config.config import Config
from poetry.core.packages.dependency_group import MAIN_GROUP
from poetry.core.packages.directory_dependency import DirectoryDependency
from poetry.core.packages.project_package import ProjectPackage
from poetry.factory import Factory
from poetry.packages.locker import Locker
from poetry.poetry import Poetry
from poetry_plugin_export.command import ExportCommand

from poetry_monoranger_plugin.path_dep_pinner import PathDepPinner

if TYPE_CHECKING:
    from cleo.events.console_command_event import ConsoleCommandEvent
    from cleo.io.io import IO
    from poetry.core.packages.dependency import Dependency
    from poetry.core.packages.package import Package

    from poetry_monoranger_plugin.config import MonorangerConfig


class PathDepPinningLocker(Locker):
    """A modified Locker that pins path dependencies in the lock file to specific versions"""

    _pinner: PathDepPinner
    _io: IO

    @classmethod
    def from_locker(cls, locker: Locker, pinner: PathDepPinner, io: IO) -> PathDepPinningLocker:
        """Creates a new PathDepPinningLocker from an existing Locker"""
        new_locker = cls.__new__(cls)
        new_locker.__dict__.update(locker.__dict__)

        new_locker._io = io
        new_locker._pinner = pinner
        return new_locker

    def _get_locked_package(self, info: dict[str, Any], with_dependencies: bool = True) -> Package:
        package = super()._get_locked_package(info, with_dependencies)

        if package.source_type == "directory":
            package._source_type = None
            package._source_url = None

            # noinspection PyProtectedMember
            if package._dependency_groups and MAIN_GROUP in package._dependency_groups:
                # noinspection PyProtectedMember
                main_deps_group = package._dependency_groups[MAIN_GROUP]
                # noinspection PyProtectedMember
                self._pinner._pin_dep_grp(main_deps_group, self._io)

        return package


class PathDepPinningPackage(ProjectPackage):
    """A modified ProjectPackage that pins path dependencies to specific versions"""

    _pinner: PathDepPinner

    @classmethod
    def from_package(cls, package: Package, pinner: PathDepPinner) -> PathDepPinningPackage:
        """Creates a new PathDepPinningPackage from an existing Package"""
        new_package = cls.__new__(cls)
        new_package.__dict__.update(package.__dict__)

        new_package._pinner = pinner
        return new_package

    @property
    def all_requires(self) -> list[Dependency]:
        """Returns the main dependencies and group dependencies
        enriched with Poetry-specific information for locking while ensuring
        path dependencies are pinned to specific versions.
        """
        deps = super().all_requires
        # noinspection PyProtectedMember
        deps = [self._pinner._pin_dependency(dep) if isinstance(dep, DirectoryDependency) else dep for dep in deps]
        return deps


class ExportModifier:
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
        assert isinstance(command, ExportCommand), (
            f"{self.__class__.__name__} can only be used for `poetry export` command"
        )

        io = event.io
        io.write_line("<info>Running command from monorepo root directory</info>")

        # Force reload global config in order to undo changes that happened due to subproject's poetry.toml configs
        _ = Config.create(reload=True)
        monorepo_root = (command.poetry.pyproject_path.parent / self.plugin_conf.monorepo_root).resolve()
        monorepo_root_poetry = Factory().create_poetry(
            cwd=monorepo_root, io=io, disable_cache=command.poetry.disable_cache
        )

        pinner = PathDepPinner(self.plugin_conf)

        # Create a copy of the poetry object to prevent the command from modifying the original poetry object
        poetry = Poetry.__new__(Poetry)
        poetry.__dict__.update(command.poetry.__dict__)
        pinning_package = PathDepPinningPackage.from_package(poetry.package, pinner)
        poetry._package = pinning_package

        pinning_locker = PathDepPinningLocker.from_locker(monorepo_root_poetry.locker, pinner, io)
        poetry.set_locker(pinning_locker)

        command.set_poetry(poetry)
