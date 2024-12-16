from pathlib import Path
from unittest.mock import Mock

import pytest
from poetry.core.packages.dependency import Dependency
from poetry.core.packages.dependency_group import MAIN_GROUP, DependencyGroup
from poetry.core.packages.directory_dependency import DirectoryDependency
from poetry.poetry import Poetry


@pytest.fixture
def mock_event_gen():
    from poetry.console.commands.command import Command

    def _factory(command_cls: type[Command], disable_cache: bool):
        from cleo.events.console_command_event import ConsoleCommandEvent

        main_grp = DependencyGroup(MAIN_GROUP)
        main_grp.add_dependency(Dependency("numpy", "==1.5.0"))
        main_grp.add_dependency(
            DirectoryDependency(
                "packageB",
                Path("../packageB"),
                develop=True,
                groups=[main_grp.name],
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
def mock_terminate_event_gen(mock_event_gen):
    from poetry.console.commands.command import Command

    def _factory(command_cls: type[Command], disable_cache: bool):
        from cleo.events.console_terminate_event import ConsoleTerminateEvent

        mock_event = mock_event_gen(command_cls, disable_cache)
        mock_io = mock_event.io
        mock_command = mock_event.command
        del mock_event

        mock_terminate_event = Mock(spec=ConsoleTerminateEvent)
        mock_terminate_event.command = mock_command
        mock_terminate_event.io = mock_io

        return mock_terminate_event

    return _factory
