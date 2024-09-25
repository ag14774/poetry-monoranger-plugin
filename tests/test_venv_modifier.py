import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from poetry.console.commands.env_command import EnvCommand
from poetry.console.commands.installer_command import InstallerCommand
from poetry.installation.installer import Installer
from poetry.poetry import Poetry

from poetry_monoranger_plugin.config import MonorangerConfig
from poetry_monoranger_plugin.venv_modifier import VenvModifier


@pytest.mark.parametrize("disable_cache", [True, False])
def test_executes_modifications_for_env_command(mock_event_gen, disable_cache: bool):
    mock_event = mock_event_gen(EnvCommand, disable_cache=disable_cache)
    mock_command = mock_event.command
    config = MonorangerConfig(enabled=True, monorepo_root="../")
    venv_modifier = VenvModifier(config)

    environ = os.environ.copy()
    environ.pop("VIRTUAL_ENV", None)
    with (
        patch("poetry_monoranger_plugin.venv_modifier.Factory.create_poetry", autospec=True) as mock_create_poetry,
        patch("poetry_monoranger_plugin.venv_modifier.EnvManager.create_venv", autospec=True) as mock_create_venv,
        patch.dict("os.environ", environ, clear=True),
    ):
        mock_create_poetry.return_value = Mock(spec=Poetry)
        mock_create_venv.return_value = Mock()

        venv_modifier.execute(mock_event)

        # create_poetry is called with the correct args
        mock_create_poetry.assert_called_once()
        assert mock_create_poetry.call_args[1]["cwd"] == Path("/monorepo_root")
        assert mock_create_poetry.call_args[1]["io"] == mock_event.io
        assert mock_create_poetry.call_args[1]["disable_cache"] == disable_cache

        # create_venv is called and EnvManager was created with the correct args
        mock_create_venv.assert_called_once()
        # Check if 'EnvManager()._poetry' contains the Mock output of mock_create_poetry.
        # Use the 'self' argument to mock_create_venv to access the 'EnvManager' instance.
        assert mock_create_venv.call_args[0][0]._poetry == mock_create_poetry.return_value

        # The new venv object is attached to the original command
        mock_command.set_env.assert_called_once()
        assert mock_command.set_env.call_args[0][0] == mock_create_venv.return_value


@pytest.mark.parametrize("disable_cache", [True, False])
def test_executes_modifications_for_installer_command(mock_event_gen, disable_cache: bool):
    mock_event = mock_event_gen(InstallerCommand, disable_cache=disable_cache)
    mock_command = mock_event.command
    config = MonorangerConfig(enabled=True, monorepo_root="../")
    venv_modifier = VenvModifier(config)

    environ = os.environ.copy()
    environ.pop("VIRTUAL_ENV", None)
    with (
        patch("poetry_monoranger_plugin.venv_modifier.Factory.create_poetry", autospec=True) as mock_create_poetry,
        patch("poetry_monoranger_plugin.venv_modifier.EnvManager.create_venv", autospec=True) as mock_create_venv,
        patch("poetry_monoranger_plugin.venv_modifier.Installer", autospec=True) as mock_installer_cls,
        patch.dict("os.environ", environ, clear=True),
    ):
        mock_create_poetry.return_value = Mock(spec=Poetry)
        mock_create_venv.return_value = Mock()
        mock_installer_cls.return_value = Mock(spec=Installer)

        venv_modifier.execute(mock_event)

        # Installer is created with all args from the original command except the env
        mock_installer_cls.assert_called_once()
        assert mock_installer_cls.call_args[0][1] == mock_create_venv.return_value
        assert mock_installer_cls.call_args[0][2] == mock_command.poetry.package
        assert mock_installer_cls.call_args[0][3] == mock_command.poetry.locker
        assert mock_installer_cls.call_args[0][4] == mock_command.poetry.pool
        assert mock_installer_cls.call_args[0][5] == mock_command.poetry.config
        assert mock_installer_cls.call_args[1]["disable_cache"] == mock_command.poetry.disable_cache

        mock_command.set_installer.assert_called_once()
        assert mock_command.set_installer.call_args[0][0] == mock_installer_cls.return_value


@pytest.mark.parametrize("disable_cache", [True, False])
def test_does_not_activate_venv_if_already_in_venv(mock_event_gen, disable_cache: bool):
    mock_event = mock_event_gen(EnvCommand, disable_cache=disable_cache)
    config = MonorangerConfig(enabled=True, monorepo_root="../")
    venv_modifier = VenvModifier(config)

    environ = os.environ.copy()
    environ["VIRTUAL_ENV"] = "/some/venv"
    with (
        patch("poetry_monoranger_plugin.venv_modifier.Factory.create_poetry", autospec=True) as mock_create_poetry,
        patch("poetry_monoranger_plugin.venv_modifier.EnvManager.create_venv", autospec=True) as mock_create_venv,
        patch.dict("os.environ", environ, clear=True),
    ):
        venv_modifier.execute(mock_event)

        mock_create_poetry.assert_not_called()
        mock_create_venv.assert_not_called()
        mock_event.command.set_env.assert_not_called()
