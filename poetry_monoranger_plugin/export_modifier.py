"""Copyright (C) 2024 GlaxoSmithKline plc

This module defines the ExportModifier class, which modifies the `poetry export` command. Similarly to
`poetry build` this exports the dependencies of a subproject to an alternative format while ensuring path
dependencies are pinned to specific versions.
"""

from __future__ import annotations

import shutil
import tempfile
import weakref
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import poetry.__version__ as poetry_version
from poetry.config.config import Config
from poetry.core.packages.dependency_group import MAIN_GROUP
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

POETRY_V2 = poetry_version.__version__.startswith("2.")

TemporaryLockerT = TypeVar("TemporaryLockerT", bound="TemporaryLocker")

if not POETRY_V2:
    from poetry.core.packages.directory_dependency import DirectoryDependency
    from poetry.core.packages.project_package import ProjectPackage

    class PathDepPinningPackage(ProjectPackage):
        """A modified ProjectPackage that pins path dependencies to specific versions

        *NOTE*: Only required for Poetry V1
        """

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


class TemporaryLocker(Locker):
    """A temporary locker that is used to store the lock file in a temporary file."""

    @classmethod
    def from_locker(cls: type[TemporaryLockerT], locker: Locker, data: dict[str, Any] | None) -> TemporaryLockerT:
        """Creates a temporary locker from an existing locker."""
        temp_file = tempfile.NamedTemporaryFile(prefix="poetry_lock_", delete=False)  # noqa: SIM115
        temp_file_path = Path(temp_file.name)
        temp_file.close()

        shutil.copy(locker.lock, temp_file_path)

        if data is None:
            data = locker._pyproject_data if POETRY_V2 else locker._local_config  # type: ignore[attr-defined]

        new_locker: TemporaryLockerT = cls(temp_file_path, data)
        weakref.finalize(new_locker, temp_file_path.unlink)

        return new_locker


def _pin_package(package: Package, pinner: PathDepPinner, io: IO) -> Package:
    """Pins a package to a specific version if it is a path dependency"""
    if package.source_type == "directory":
        package._source_type = None
        package._source_url = None

        # noinspection PyProtectedMember
        if package._dependency_groups and MAIN_GROUP in package._dependency_groups:
            # noinspection PyProtectedMember
            main_deps_group = package._dependency_groups[MAIN_GROUP]
            # noinspection PyProtectedMember
            pinner._pin_dep_grp(main_deps_group, io)
    return package


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

        # Create a copy of the poetry object to prevent the command from modifying the original poetry object
        poetry = Poetry.__new__(Poetry)
        poetry.__dict__.update(command.poetry.__dict__)

        # Force reload global config in order to undo changes that happened due to subproject's poetry.toml configs
        _ = Config.create(reload=True)
        monorepo_root = (command.poetry.pyproject_path.parent / self.plugin_conf.monorepo_root).resolve()
        monorepo_root_poetry = Factory().create_poetry(
            cwd=monorepo_root, io=io, disable_cache=command.poetry.disable_cache
        )

        if POETRY_V2:
            temp_locker = TemporaryLocker.from_locker(monorepo_root_poetry.locker, poetry.pyproject.data)
        else:
            temp_locker = TemporaryLocker.from_locker(monorepo_root_poetry.locker, poetry.pyproject.poetry_config)

        from poetry.puzzle.solver import Solver

        locked_repository = monorepo_root_poetry.locker.locked_repository()
        solver = Solver(
            poetry.package,
            poetry.pool,
            locked_repository.packages,
            locked_repository.packages,
            io,
        )

        # Always re-solve directory dependencies, otherwise we can't determine
        # if anything has changed (and the lock file contains an invalid version).
        use_latest = [p.name for p in locked_repository.packages if p.source_type == "directory"]
        pinner = PathDepPinner(self.plugin_conf)
        if POETRY_V2:
            packages = solver.solve(use_latest=use_latest).get_solved_packages()  # type: ignore[attr-defined]
            packages = {_pin_package(pak, pinner, io): info for pak, info in packages.items()}
        else:
            from poetry.installation.operations import Uninstall, Update
            from poetry.repositories.lockfile_repository import LockfileRepository

            ops = solver.solve(use_latest=use_latest).calculate_operations()
            packages = [
                op.target_package if isinstance(op, Update) else op.package
                for op in ops
                if not isinstance(op, Uninstall)
            ]

            lockfile_repo = LockfileRepository()
            for package in packages:
                if not lockfile_repo.has_package(package):
                    lockfile_repo.add_package(package)

            packages = [_pin_package(pak, pinner, io) for pak in lockfile_repo.packages]

        if not POETRY_V2:
            poetry._package = PathDepPinningPackage.from_package(poetry.package, pinner)

        temp_locker.set_lock_data(poetry.package, packages)
        poetry.set_locker(temp_locker)
        command.set_poetry(poetry)
