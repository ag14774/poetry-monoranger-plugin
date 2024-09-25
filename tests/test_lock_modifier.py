from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from poetry.console.commands.lock import LockCommand
from poetry.installation.installer import Installer
from poetry.poetry import Poetry

from poetry_monoranger_plugin.config import MonorangerConfig
from poetry_monoranger_plugin.lock_modifier import LockModifier


@pytest.mark.parametrize("disable_cache", [True, False])
def test_executes_modifications_for_lock_command(mock_event_gen, disable_cache: bool):
    mock_event = mock_event_gen(LockCommand, disable_cache=disable_cache)
    mock_command = mock_event.command
    config = MonorangerConfig(enabled=True, monorepo_root="../")
    lock_modifier = LockModifier(config)

    with (
        patch("poetry_monoranger_plugin.lock_modifier.Factory.create_poetry", autospec=True) as mock_create_poetry,
        patch("poetry_monoranger_plugin.lock_modifier.Installer", autospec=True) as mock_installer_cls,
    ):
        mock_create_poetry.return_value = Mock(spec=Poetry)
        mock_installer_cls.return_value = Mock(spec=Installer)

        lock_modifier.execute(mock_event)

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

        # The new poetry and installer objects should be set on the command
        assert mock_command.set_poetry.call_args[0][0] == mock_create_poetry.return_value
        assert mock_command.set_installer.call_args[0][0] == mock_installer_cls.return_value
