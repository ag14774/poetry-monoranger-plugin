"""Copyright (C) 2024 GlaxoSmithKline plc

This module is the entry point for the monoranger plugin. It defines the Monoranger class,
which is an *application* plugin for Poetry.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

import cleo.events.console_events
from cleo.events.console_command_event import ConsoleCommandEvent
from cleo.events.console_terminate_event import ConsoleTerminateEvent
from poetry.console.commands.add import AddCommand
from poetry.console.commands.build import BuildCommand
from poetry.console.commands.env_command import EnvCommand
from poetry.console.commands.install import InstallCommand
from poetry.console.commands.lock import LockCommand
from poetry.console.commands.remove import RemoveCommand
from poetry.console.commands.self.self_command import SelfCommand
from poetry.console.commands.update import UpdateCommand
from poetry.plugins.application_plugin import ApplicationPlugin

from poetry_monoranger_plugin.config import MonorangerConfig

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cleo.events.event import Event
    from cleo.events.event_dispatcher import EventDispatcher
    from poetry.console.application import Application
    from poetry.console.commands.command import Command as PoetryCommand
    from poetry.poetry import Poetry


def _default_plugin_config():
    return {"tool": {"poetry-monoranger-plugin": {"enabled": False}}}


def _merge_dicts(base: Mapping, addition: Mapping) -> Mapping:
    result = dict(copy.deepcopy(base))
    for key, value in addition.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            result[key] = _merge_dicts(base[key], value)
        else:
            result[key] = value
    return result


class Monoranger(ApplicationPlugin):
    """The main class of the Monoranger plugin."""

    def __init__(self):
        super().__init__()

        self.poetry: Poetry = None  # type: ignore[assignment]
        self.plugin_conf: MonorangerConfig = None  # type: ignore[assignment]
        self.ctx: dict[type[PoetryCommand], Any] = {}

    def activate(self, application: Application):
        """The entry point of the plugin. This is called by Poetry when the plugin is activated.

        Args:
            application: The Poetry application instance.
        """
        try:
            local_poetry_proj_config = application.poetry.pyproject.data
        except RuntimeError:
            # Not in a valid poetry project
            return

        plugin_config = _merge_dicts(_default_plugin_config(), local_poetry_proj_config)["tool"][
            "poetry-monoranger-plugin"
        ]
        if not plugin_config["enabled"]:
            return

        assert application.event_dispatcher is not None
        application.event_dispatcher.add_listener(
            cleo.events.console_events.COMMAND, self.console_command_event_listener
        )
        application.event_dispatcher.add_listener(
            cleo.events.console_events.TERMINATE, self.post_console_command_event_listener
        )

        self.poetry = application.poetry
        self.plugin_conf = MonorangerConfig.from_dict(plugin_config)

    def console_command_event_listener(self, event: Event, event_name: str, dispatcher: EventDispatcher):
        """The event listener for console commands. This is executed before the command is run.

        Args:
            event: The event object.
            event_name: The name of the event.
            dispatcher: The event dispatcher.
        """
        assert isinstance(event, ConsoleCommandEvent)
        command = event.command

        if isinstance(command, EnvCommand) and not isinstance(command, SelfCommand):
            from poetry_monoranger_plugin.venv_modifier import VenvModifier

            VenvModifier(self.plugin_conf).execute(event)

        if isinstance(command, (LockCommand, InstallCommand, UpdateCommand)):
            from poetry_monoranger_plugin.lock_modifier import LockModifier

            # NOTE: consider moving this to a separate UpdateModifier class
            if isinstance(command, UpdateCommand) and not event.io.input._arguments.get("packages", None):
                event.io.input._arguments["packages"] = [command.poetry.package.name]
            LockModifier(self.plugin_conf).execute(event)

        if isinstance(command, (AddCommand, RemoveCommand)):
            from poetry_monoranger_plugin.monorepo_adder import MonorepoAdderRemover

            adder_remover = MonorepoAdderRemover(self.plugin_conf)
            self.ctx[AddCommand] = adder_remover

            adder_remover.execute(event)

        if isinstance(command, BuildCommand):
            from poetry_monoranger_plugin.path_rewriter import PathRewriter

            PathRewriter(self.plugin_conf).execute(event)

    def post_console_command_event_listener(self, event: Event, event_name: str, dispatcher: EventDispatcher):
        """The event listener for console commands. This is executed after the command is run.

        Args:
            event: The event object.
            event_name: The name of the event.
            dispatcher: The event dispatcher.
        """
        assert isinstance(event, ConsoleTerminateEvent)
        command = event.command

        if isinstance(command, (AddCommand, RemoveCommand)):
            from poetry_monoranger_plugin.monorepo_adder import MonorepoAdderRemover

            adder_remover = self.ctx.pop(AddCommand, MonorepoAdderRemover(self.plugin_conf))
            adder_remover.post_execute(event)
