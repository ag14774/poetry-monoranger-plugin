"""Copyright (C) 2024 GlaxoSmithKline plc

This module defines the PathRewriter class, which modifies the behavior of the Poetry build command to
rewrite directory dependencies to their pinned versions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from poetry.console.commands.build import BuildCommand
from poetry.core.constraints.version import Version
from poetry.core.packages.dependency import Dependency
from poetry.core.packages.dependency_group import MAIN_GROUP
from poetry.core.packages.directory_dependency import DirectoryDependency
from poetry.core.pyproject.toml import PyProjectTOML

if TYPE_CHECKING:
    from cleo.events.console_command_event import ConsoleCommandEvent
    from poetry.poetry import Poetry

    from poetry_monoranger_plugin.config import MonorangerConfig


class PathRewriter:
    """A class to handle the rewriting of directory dependencies in a Poetry project."""

    def __init__(self, plugin_conf: MonorangerConfig):
        self.plugin_conf: MonorangerConfig = plugin_conf

    def execute(self, event: ConsoleCommandEvent):
        """Executes the path rewriting process during the Poetry build command.

        Args:
            event (ConsoleCommandEvent): The triggering event.
        """
        command = event.command
        assert isinstance(
            command, BuildCommand
        ), f"{self.__class__.__name__} can only be used with the `poetry build` command"

        io = event.io
        poetry = command.poetry

        main_deps_group = poetry.package.dependency_group(MAIN_GROUP)
        directory_deps = [dep for dep in main_deps_group.dependencies if isinstance(dep, DirectoryDependency)]

        for dependency in directory_deps:
            try:
                pinned = self._pin_dependency(poetry, dependency)
            except (RuntimeError, ValueError) as e:
                io.write_line(f"<fg=yellow>Could not pin dependency {dependency.name}: {e!s}</>")
                continue

            main_deps_group.remove_dependency(dependency.name)
            main_deps_group.add_dependency(pinned)

    def _get_dependency_pyproject(self, poetry: Poetry, dependency: DirectoryDependency) -> PyProjectTOML:
        pyproject_file = poetry.pyproject_path.parent / dependency.path / "pyproject.toml"

        if not pyproject_file.exists():
            raise RuntimeError(f"Could not find pyproject.toml in {dependency.path}")

        dep_pyproject: PyProjectTOML = PyProjectTOML(pyproject_file)

        if not dep_pyproject.is_poetry_project():
            raise RuntimeError(f"Directory {dependency.path} is not a valid poetry project")

        return dep_pyproject

    def _pin_dependency(self, poetry: Poetry, dependency: DirectoryDependency):
        """Pins a directory dependency to a specific version based on the plugin configuration.

        Args:
            poetry (Poetry): The Poetry instance.
            dependency (DirectoryDependency): The directory dependency to pin.

        Returns:
            Dependency: The pinned dependency.

        Raises:
            RuntimeError: If the pyproject.toml file is not found or is not a valid Poetry project.
            ValueError: If the version rewrite rule is invalid.
        """
        dep_pyproject: PyProjectTOML = self._get_dependency_pyproject(poetry, dependency)

        name = cast(str, dep_pyproject.poetry_config["name"])
        version = cast(str, dep_pyproject.poetry_config["version"])
        if self.plugin_conf.version_rewrite_rule in ["~", "^"]:
            pinned_version = f"{self.plugin_conf.version_rewrite_rule}{version}"
        elif self.plugin_conf.version_rewrite_rule == "==":
            pinned_version = version
        elif self.plugin_conf.version_rewrite_rule == ">=,<":
            parsed_version = Version.parse(version)
            next_patch_version = parsed_version.replace(dev=None, pre=None).next_patch()
            pinned_version = f">={version},<{next_patch_version}"
        else:
            raise ValueError(f"Invalid version rewrite rule: {self.plugin_conf.version_rewrite_rule}")

        return Dependency(name, pinned_version, groups=dependency.groups)
