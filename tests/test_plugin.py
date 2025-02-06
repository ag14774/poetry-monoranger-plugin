from unittest.mock import Mock, patch

import pytest
from poetry.console.commands.add import AddCommand
from poetry.console.commands.build import BuildCommand
from poetry.console.commands.command import Command
from poetry.console.commands.env_command import EnvCommand
from poetry.console.commands.install import InstallCommand
from poetry.console.commands.lock import LockCommand
from poetry.console.commands.remove import RemoveCommand
from poetry.console.commands.update import UpdateCommand

from poetry_monoranger_plugin.config import MonorangerConfig
from poetry_monoranger_plugin.plugin import Monoranger


def test_activates_plugin_with_valid_config():
    application = Mock()
    application.poetry.pyproject.data = {
        "tool": {"poetry-monoranger-plugin": {"enabled": True, "monorepo_root": "../"}}
    }
    application.event_dispatcher = Mock()
    plugin = Monoranger()
    plugin.activate(application)

    assert plugin.plugin_conf.enabled is True
    assert plugin.plugin_conf.monorepo_root == "../"
    application.event_dispatcher.add_listener.assert_called()


def test_does_not_activate_plugin_with_disabled_config():
    application = Mock()
    application.poetry.pyproject.data = {}
    application.event_dispatcher = Mock()
    plugin = Monoranger()
    plugin.activate(application)

    assert plugin.plugin_conf is None
    application.event_dispatcher.add_listener.assert_not_called()


@pytest.mark.parametrize(
    "cmd_type",
    [
        AddCommand,
        RemoveCommand,
        BuildCommand,
        EnvCommand,
        LockCommand,
        InstallCommand,
        UpdateCommand,
    ],
)
def test_handles_all_command_events(mock_event_gen, cmd_type: type[Command]):
    cmd_to_patch: dict[type[Command], str] = {
        AddCommand: "poetry_monoranger_plugin.monorepo_adder.MonorepoAdderRemover.execute",
        RemoveCommand: "poetry_monoranger_plugin.monorepo_adder.MonorepoAdderRemover.execute",
        BuildCommand: "poetry_monoranger_plugin.path_dep_pinner.PathDepPinner.execute",
        EnvCommand: "poetry_monoranger_plugin.venv_modifier.VenvModifier.execute",
        LockCommand: "poetry_monoranger_plugin.lock_modifier.LockModifier.execute",
        InstallCommand: "poetry_monoranger_plugin.lock_modifier.LockModifier.execute",
        UpdateCommand: "poetry_monoranger_plugin.lock_modifier.LockModifier.execute",
    }
    event = mock_event_gen(cmd_type, disable_cache=False)
    plugin = Monoranger()
    plugin.plugin_conf = MonorangerConfig(enabled=True, monorepo_root="../")
    with patch(cmd_to_patch[cmd_type]) as mock_execute:
        plugin.console_command_event_listener(event, "", Mock())
        mock_execute.assert_called_once_with(event)
