"""Copyright (C) 2024 GlaxoSmithKline plc

This module defines the PathDepPinner class, which modifies the behavior of the Poetry build command to
remove the path component of directory dependencies and replace it with a pinned version.
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, cast

import poetry.__version__ as poetry_version
from poetry.console.commands.build import BuildCommand
from poetry.core.constraints.version import Version
from poetry.core.packages.dependency import Dependency
from poetry.core.packages.dependency_group import MAIN_GROUP
from poetry.core.packages.directory_dependency import DirectoryDependency
from poetry.core.pyproject.toml import PyProjectTOML

with suppress(ImportError):
    from poetry.core.pyproject.exceptions import PyProjectError  # type: ignore[attr-defined]  # exists only in >=2.0.0

if TYPE_CHECKING:
    from cleo.events.console_command_event import ConsoleCommandEvent
    from cleo.io.io import IO
    from poetry.core.packages.dependency_group import DependencyGroup

    from poetry_monoranger_plugin.config import MonorangerConfig

POETRY_V2 = poetry_version.__version__.startswith("2.")


class PathDepPinner:
    """A class to handle the pinning of directory dependencies in a Poetry project."""

    def __init__(self, plugin_conf: MonorangerConfig):
        self.plugin_conf: MonorangerConfig = plugin_conf

    def execute(self, event: ConsoleCommandEvent):
        """Executes the version pinning process of path dependencies during the Poetry build command.

        Args:
            event (ConsoleCommandEvent): The triggering event.
        """
        command = event.command
        assert isinstance(command, BuildCommand), (
            f"{self.__class__.__name__} can only be used with the `poetry build` command"
        )

        io = event.io
        poetry = command.poetry

        main_deps_group = poetry.package.dependency_group(MAIN_GROUP)
        self._pin_dep_grp(main_deps_group, io)

    def _pin_dep_grp(self, dep_gpr: DependencyGroup, io: IO):
        directory_deps = self._get_directory_deps(dep_gpr)

        for dependency in directory_deps:
            try:
                pinned = self._pin_dependency(dependency)
            except (RuntimeError, ValueError) as e:
                io.write_line(f"<fg=yellow>Could not pin dependency {dependency.name}: {e!s}</>")
                continue

            dep_gpr.remove_dependency(dependency.name)
            dep_gpr.add_dependency(pinned)

    @staticmethod
    def _get_directory_deps(dep_grp: DependencyGroup) -> list[DirectoryDependency]:
        if not POETRY_V2:
            return [dep for dep in dep_grp.dependencies if isinstance(dep, DirectoryDependency)]

        # Collect extras
        features: defaultdict[str, set] = defaultdict(set)
        for dep_set in [dep_grp._poetry_dependencies, dep_grp.dependencies, dep_grp.dependencies_for_locking]:  # type: ignore[attr-defined]
            # Collect all extras for each dependency from all three ways of accessing deps
            # (._poetry_dependencies, .dependencies, .dependencies_for_locking)
            if dep_set is not None:
                for dep in dep_set:
                    if dep.features:
                        features[dep.name].update(dep.features)

        # Required to have type: ignore[attr-defined] as the attribute is only defined in Poetry >=2.0.0
        deps_for_locking = {dep.name: dep for dep in dep_grp.dependencies_for_locking}  # type: ignore[attr-defined]

        directory_deps = []
        for dep in dep_grp.dependencies:
            if isinstance(dep, DirectoryDependency):
                dir_dep = dep
            elif isinstance(deps_for_locking.get(dep.name, None), DirectoryDependency):
                dir_dep = cast(DirectoryDependency, deps_for_locking[dep.name])
            else:
                continue

            directory_deps.append(dir_dep.with_features(features[dir_dep.name]))

        return directory_deps

    @staticmethod
    def _get_dependency_pyproject(dependency: DirectoryDependency) -> PyProjectTOML:
        assert dependency.source_url is not None
        pyproject_file = Path(dependency.source_url) / "pyproject.toml"

        if not pyproject_file.exists():
            raise RuntimeError(f"Could not find pyproject.toml in {dependency.path}")

        dep_pyproject: PyProjectTOML = PyProjectTOML(pyproject_file)

        if not dep_pyproject.is_poetry_project():
            raise RuntimeError(f"Directory {dependency.path} is not a valid poetry project")

        return dep_pyproject

    def _pin_dependency(self, dependency: DirectoryDependency):
        """Pins a directory dependency to a specific version based on the plugin configuration.

        Args:
            dependency (DirectoryDependency): The directory dependency to pin.

        Returns:
            Dependency: The pinned dependency.

        Raises:
            RuntimeError: If the pyproject.toml file is not found or is not a valid Poetry project.
            ValueError: If the version pinning rule is invalid.
        """
        dep_pyproject: PyProjectTOML = self._get_dependency_pyproject(dependency)

        try:
            name = cast(str, dep_pyproject.poetry_config["name"])
            version = cast(str, dep_pyproject.poetry_config["version"])
        except PyProjectError:
            # Fallback to the project section since Poetry V2 also supports PEP 621 pyproject.toml files
            name = cast(str, dep_pyproject.data["project"]["name"])
            version = cast(str, dep_pyproject.data["project"]["version"])

        if self.plugin_conf.version_pinning_rule in ["~", "^"]:
            pinned_version = f"{self.plugin_conf.version_pinning_rule}{version}"
        elif self.plugin_conf.version_pinning_rule == "==":
            pinned_version = version
        elif self.plugin_conf.version_pinning_rule == ">=,<":
            parsed_version = Version.parse(version)
            next_patch_version = parsed_version.replace(dev=None, pre=None).next_patch()
            pinned_version = f">={version},<{next_patch_version}"
        else:
            raise ValueError(f"Invalid version pinning rule: {self.plugin_conf.version_pinning_rule}")

        return Dependency(
            name,
            pinned_version,
            groups=dependency.groups,
            optional=dependency.is_optional(),
            extras=dependency.extras,
        )
