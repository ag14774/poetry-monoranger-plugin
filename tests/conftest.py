from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from cleo.events.console_command_event import ConsoleCommandEvent
from poetry.core.packages.dependency import Dependency
from poetry.core.packages.dependency_group import MAIN_GROUP, DependencyGroup
from poetry.core.packages.directory_dependency import DirectoryDependency
from poetry.poetry import Poetry

from tests.helpers import MockRepoManager, _poetry_run

if TYPE_CHECKING:
    from poetry.console.commands.command import Command


@pytest.fixture
def mock_event_gen():
    def _factory(command_cls: type[Command], disable_cache: bool):
        main_grp = DependencyGroup(MAIN_GROUP)
        main_grp.add_dependency(Dependency("numpy", "==1.5.0"))
        main_grp.add_dependency(
            DirectoryDependency(
                "packageB",
                Path("../packageB"),
                develop=True,
                optional=True,
                extras=["fast"],
            )
        )

        mock_command = Mock(spec=command_cls)
        mock_command.poetry = Mock(spec=Poetry)
        mock_command.poetry.pyproject_path = Path("/monorepo_root/packageA/pyproject.toml")
        mock_command.poetry.package = Mock()
        mock_command.poetry.package.name = "packageA"
        mock_command.poetry.package.dependency_group = Mock()
        mock_command.poetry.package.dependency_group.return_value = main_grp
        mock_command.poetry.locker = Mock()
        mock_command.poetry.pool = Mock()
        mock_command.poetry.config = Mock()
        mock_command.poetry.disable_cache = disable_cache
        mock_command.option = Mock(return_value=False)

        mock_io = Mock()

        mock_event = Mock(spec=ConsoleCommandEvent)
        mock_event.command = mock_command
        mock_event.io = mock_io

        return mock_event

    return _factory


@pytest.fixture
def poetry_run():
    return _poetry_run


@pytest.fixture(scope="session")
def repo_manager():
    obj = MockRepoManager()
    yield obj
    del obj
