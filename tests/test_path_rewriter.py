import copy
from unittest.mock import Mock, patch

import pytest
from poetry.console.commands.build import BuildCommand
from poetry.core.packages.directory_dependency import DirectoryDependency
from poetry.core.pyproject.toml import PyProjectTOML

from poetry_monoranger_plugin.config import MonorangerConfig
from poetry_monoranger_plugin.path_rewriter import PathRewriter


@pytest.mark.parametrize("disable_cache", [True, False])
def test_executes_path_rewriting_for_build_command(mock_event_gen, disable_cache: bool):
    mock_event = mock_event_gen(BuildCommand, disable_cache=disable_cache)
    mock_command = mock_event.command
    config = MonorangerConfig(enabled=True, monorepo_root="../", version_rewrite_rule="==")
    path_rewriter = PathRewriter(config)

    original_dependencies = copy.deepcopy(mock_command.poetry.package.dependency_group.return_value.dependencies)

    with patch(
        "poetry_monoranger_plugin.path_rewriter.PathRewriter._get_dependency_pyproject", autospec=True
    ) as mock_get_dep:
        mock_get_dep.return_value = Mock(spec=PyProjectTOML)
        mock_get_dep.return_value.poetry_config = {"version": "0.1.0", "name": "packageB"}

        path_rewriter.execute(mock_event)

    new_dependencies = mock_command.poetry.package.dependency_group.return_value

    assert len(new_dependencies.dependencies) == len(original_dependencies)
    # sort the dependencies by name to ensure they are in the same order
    original_dependencies = sorted(original_dependencies, key=lambda x: x.name)
    new_dependencies = sorted(new_dependencies.dependencies, key=lambda x: x.name)
    for i, dep in enumerate(new_dependencies):
        assert dep.name == original_dependencies[i].name
        assert dep.is_optional() == original_dependencies[i].is_optional()
        assert dep.extras == original_dependencies[i].extras
        if isinstance(original_dependencies[i], DirectoryDependency):
            assert dep.pretty_constraint == "0.1.0"
        else:
            assert dep.pretty_constraint == original_dependencies[i].pretty_constraint
