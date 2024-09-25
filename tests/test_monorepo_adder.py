from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from poetry.console.commands.add import AddCommand
from poetry.installation.installer import Installer
from poetry.poetry import Poetry

from poetry_monoranger_plugin.config import MonorangerConfig
from poetry_monoranger_plugin.monorepo_adder import DummyInstaller, MonorepoAdderRemover


@pytest.mark.parametrize("disable_cache", [True, False])
def test_executes_modifications_for_addremove_command(mock_event_gen, disable_cache: bool):
    mock_event = mock_event_gen(AddCommand, disable_cache=disable_cache)
    mock_command = mock_event.command
    config = MonorangerConfig(enabled=True, monorepo_root="../")
    adder_remover = MonorepoAdderRemover(config)

    with patch("poetry_monoranger_plugin.monorepo_adder.Poetry.__new__", autospec=True) as mock_poetry:
        mock_poetry.return_value = Mock(spec=Poetry)

        adder_remover.execute(mock_event)

        mock_poetry.assert_called_once()
        assert mock_command.set_poetry.call_args[0][0] == mock_poetry.return_value
        assert isinstance(mock_command.set_installer.call_args[0][0], DummyInstaller)


@pytest.mark.parametrize("disable_cache", [True, False])
def test_executes_modifications_post_addremove_command(mock_terminate_event_gen, disable_cache: bool):
    # Here we test the .post_execute command
    mock_event = mock_terminate_event_gen(AddCommand, disable_cache=disable_cache)
    mock_command = mock_event.command
    config = MonorangerConfig(enabled=True, monorepo_root="../")
    adder_remover = MonorepoAdderRemover(config)

    with (
        patch("poetry_monoranger_plugin.monorepo_adder.Factory.create_poetry", autospec=True) as mock_create_poetry,
        patch("poetry_monoranger_plugin.monorepo_adder.Installer", autospec=True) as mock_installer_cls,
    ):
        mock_create_poetry.return_value = Mock(spec=Poetry)
        mock_installer_cls.return_value = Mock(spec=Installer)

        adder_remover.post_execute(mock_event)

        # A new poetry project object at the monorepo root should be created
        mock_create_poetry.assert_called_once()
        assert mock_create_poetry.call_args[1]["cwd"] == Path("/monorepo_root").resolve()
        assert mock_create_poetry.call_args[1]["io"] == mock_event.io
        assert mock_create_poetry.call_args[1]["disable_cache"] == disable_cache

        # A new installer should be created with the monorepo root poetry project
        mock_installer_cls.assert_called_once()
        # Env is remained unchanged as it is the responsibility of venv_modifier.py
        assert mock_installer_cls.call_args[0][1] == mock_command.env
        assert mock_installer_cls.call_args[0][2] == mock_create_poetry.return_value.package
        assert mock_installer_cls.call_args[0][3] == mock_create_poetry.return_value.locker
        assert mock_installer_cls.call_args[0][4] == mock_create_poetry.return_value.pool
        assert mock_installer_cls.call_args[0][5] == mock_create_poetry.return_value.config
        assert mock_installer_cls.call_args[1]["disable_cache"] == mock_create_poetry.return_value.disable_cache

        # Check settings of installer
        assert mock_installer_cls.return_value.dry_run.call_args[0][0] == mock_command.option("dry-run")
        assert mock_installer_cls.return_value.verbose.call_args[0][0] == mock_event.io.is_verbose()
        assert mock_installer_cls.return_value.update.call_args[0][0] is True
        assert mock_installer_cls.return_value.execute_operations.call_args[0][0] is not mock_command.option("lock")

        # The whitelist should contain the package name
        assert mock_installer_cls.return_value.whitelist.call_args[0][0] == [mock_command.poetry.package.name]

        # The installer should be run
        assert mock_installer_cls.return_value.run.call_count == 1
