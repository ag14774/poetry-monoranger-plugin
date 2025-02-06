from __future__ import annotations

import contextlib
import io
import os
import shutil
import tempfile
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import poetry.__version__
import pytest
from cleo.events.console_command_event import ConsoleCommandEvent
from cleo.events.console_events import COMMAND
from cleo.io.inputs.argv_input import ArgvInput
from cleo.io.outputs.stream_output import StreamOutput
from poetry.console.application import Application
from poetry.factory import Factory
from poetry.utils.env import EnvManager
from poetry.utils.env.system_env import SystemEnv

if TYPE_CHECKING:
    from cleo.events.event import Event
    from cleo.events.event_dispatcher import EventDispatcher
    from poetry.console.commands.command import Command
    from poetry.utils.env.base_env import Env

POETRY_V2 = poetry.__version__.__version__.startswith("2")
only_poetry_v2 = pytest.mark.skipif(POETRY_V2 is False, reason="requires poetry 2.0.0 or higher")


class MockApplication(Application):
    """A mock application that stored the last command class that was executed

    Not currently used in tests but could be useful in the future
    """

    def __init__(self):
        super().__init__()
        dispatcher = self.event_dispatcher
        if dispatcher is not None:
            dispatcher.add_listener(COMMAND, self.configure_command_spy)

        self._last_cmd: Command = None  # type: ignore[assignment]

    def configure_command_spy(self, event: Event, event_name: str, _: EventDispatcher) -> None:
        """Store the last command class that was executed"""
        if isinstance(event, ConsoleCommandEvent):
            self._last_cmd = event.command  # type: ignore[assignment]


class MockRepoManager:
    """A helper class to generate test repositories"""

    def __init__(self):
        self._src_repos: dict[str, Path] = {"v1": None, "v1_v2lock": None, "v2": None}  # type: ignore[assignment, dict-item]
        self._preinstalled_repos: dict[str, Path] = {"v1": None, "v1_v2lock": None, "v2": None}  # type: ignore[assignment, dict-item]

        self._tmp_path_obj = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp_path_obj.name)

        for repo in self._src_repos:
            src = Path(__file__).parent / "fixtures" / repo
            self._src_repos[repo] = src

        for repo, src in self._src_repos.items():
            dst = self._tmp_path / "preinstalled" / repo
            dst.mkdir(parents=True, exist_ok=True)

            shutil.copytree(src, dst, dirs_exist_ok=True)
            _poetry_run(dst, None, "install")
            self._preinstalled_repos[repo] = dst

        weakref.finalize(self, self._tmp_path_obj.cleanup)

    def get_repo(self, repo: str, preinstalled: bool = False):
        """Create a test monorepo and return the path to it

        If preinstalled is True, the monorepo will have its dependencies
        preinstalled (i.e. poetry install will be executed)
        """
        src = self._preinstalled_repos[repo] if preinstalled else self._src_repos[repo]

        dst = Path(tempfile.mkdtemp(prefix=f"{repo}_", dir=self._tmp_path))
        shutil.copytree(src, dst, dirs_exist_ok=True)

        if preinstalled:
            _poetry_run(dst, None, "install")

        return dst

    @staticmethod
    def get_envs(path: Path) -> EnvCollection:
        """Get the root and package environments for a monorepo"""
        copied_env = os.environ.copy()
        copied_env.pop("VIRTUAL_ENV", None)
        copied_env.pop("CONDA_PREFIX", None)
        copied_env.pop("CONDA_DEFAULT_ENV", None)
        with patch.dict(os.environ, copied_env, clear=True):
            root_env: Env = EnvManager(Factory().create_poetry(cwd=path)).get()
            envs: list[Env] = []
            for pkg in path.iterdir():
                if pkg.is_dir() and (pkg / "pyproject.toml").exists():
                    envs.append(EnvManager(Factory().create_poetry(cwd=pkg)).get())

        return EnvCollection(root_env, envs)


@dataclass(frozen=True)
class PoetryRunResult:
    """The result of running a poetry command"""

    cmd: str
    cmd_obj: Command
    run_dir: Path
    stdout: str
    stderr: str
    exit_code: int


@dataclass(frozen=True)
class EnvCollection:
    """A collection of environments for a monorepo"""

    root_env: Env
    pkg_envs: list[Env]


@contextlib.contextmanager
def new_cd(direc: str | Path):
    """Context manager to temporarily change the current working directory"""
    curr_dir = os.getcwd()
    os.chdir(str(direc))
    try:
        yield
    finally:
        os.chdir(str(curr_dir))


def _poetry_run(monorepo_root: Path, sub_project: str | None = None, cmd: str = "help"):
    """Run a poetry command in a monorepo

    Args:
        monorepo_root (Path): The path to the monorepo
        sub_project (str, optional): The subproject to run the command in. Defaults to None.
        cmd (str, optional): The command to run. Defaults to "help".
    """
    pkg_dir = monorepo_root / sub_project if sub_project else monorepo_root
    cmd = f"poetry {cmd}"

    input_stream = io.StringIO()
    input_obj = ArgvInput(cmd.split(" "))
    input_obj.set_stream(input_stream)

    output_stream = io.StringIO()
    error_stream = io.StringIO()

    # NO_COLOR is set to prevent a call to StreamOutput._has_color_support which causes
    # an error on Windows when stream is not sys.stdout or sys.stderr
    with patch.dict(os.environ, {"NO_COLOR": "1"}):
        output_obj = StreamOutput(output_stream, decorated=False)
        error_obj = StreamOutput(error_stream, decorated=False)

    copied_env = os.environ.copy()
    copied_env.pop("VIRTUAL_ENV", None)
    copied_env.pop("CONDA_PREFIX", None)
    copied_env.pop("CONDA_DEFAULT_ENV", None)
    with new_cd(pkg_dir), patch.dict(os.environ, copied_env, clear=True):
        app = MockApplication()
        app.auto_exits(False)
        exit_code = app.run(input_obj, output_obj, error_obj)

    return PoetryRunResult(
        cmd=cmd,
        cmd_obj=app._last_cmd,
        run_dir=pkg_dir,
        stdout=output_stream.getvalue(),
        stderr=error_stream.getvalue(),
        exit_code=exit_code,
    )


def is_system_env(env: Env) -> bool:
    return isinstance(env, SystemEnv) or (hasattr(env, "_child_env") and isinstance(env._child_env, SystemEnv))
