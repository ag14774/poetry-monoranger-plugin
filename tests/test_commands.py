from __future__ import annotations

import tarfile

from tests.helpers import is_system_env


def test_add(repo_manager, poetry_run):
    # Arrange
    v1_dir = repo_manager.get_repo("v1", preinstalled=True)
    envs = repo_manager.get_envs(v1_dir)
    root_lock = (v1_dir / "poetry.lock").read_text()
    root_pyproject = (v1_dir / "pyproject.toml").read_text()

    assert envs.root_env.site_packages.find_distribution("numpy") is None
    for env in envs.pkg_envs:
        assert env.site_packages.find_distribution("numpy") is None

    # Act
    result = poetry_run(v1_dir, "pkg_one", "add numpy==1.25")

    # Assert
    assert result.exit_code == 0
    assert "Installing numpy" in result.stdout
    assert "Skipping virtualenv creation" in result.stderr
    assert root_lock != (v1_dir / "poetry.lock").read_text()  # lock file is modified
    assert not (v1_dir / "pkg_one" / "poetry.lock").exists()  # pkg_one lockfile is not created
    assert root_pyproject == (v1_dir / "pyproject.toml").read_text()  # root pyproject.toml is not modified
    assert (v1_dir / "pkg_one" / "pyproject.toml").read_text().count("numpy") == 1  # pkg_one pyproject.toml is modified
    assert envs.root_env.site_packages.find_distribution("numpy") is not None
    for env in envs.pkg_envs:
        assert env.site_packages.find_distribution("numpy") is None


def test_remove(repo_manager, poetry_run):
    # Arrange
    v1_dir = repo_manager.get_repo("v1", preinstalled=True)
    envs = repo_manager.get_envs(v1_dir)
    root_lock = (v1_dir / "poetry.lock").read_text()
    root_pyproject = (v1_dir / "pyproject.toml").read_text()

    assert envs.root_env.site_packages.find_distribution("tqdm") is not None
    for env in envs.pkg_envs:
        assert env.site_packages.find_distribution("tqdm") is None

    # Act
    result = poetry_run(v1_dir, "pkg_two", "remove tqdm")

    # Assert
    assert result.exit_code == 0
    assert "Removing tqdm" in result.stdout
    assert "Skipping virtualenv creation" in result.stderr
    assert root_lock != (v1_dir / "poetry.lock").read_text()  # lock file is modified
    assert not (v1_dir / "pkg_two" / "poetry.lock").exists()  # pkg_two lockfile is not created
    assert root_pyproject == (v1_dir / "pyproject.toml").read_text()  # root pyproject.toml is not modified
    assert (v1_dir / "pkg_two" / "pyproject.toml").read_text().count("tqdm") == 0  # pkg_two pyproject.toml is modified
    assert envs.root_env.site_packages.find_distribution("tqdm") is None
    for env in envs.pkg_envs:
        assert env.site_packages.find_distribution("numpy") is None


def test_update(repo_manager, poetry_run):
    # Arrange
    v1_dir = repo_manager.get_repo("v1", preinstalled=True)
    envs = repo_manager.get_envs(v1_dir)

    poetry_run(v1_dir, "pkg_one", "add numpy<=1.25")
    pkg_one_pyproject = (v1_dir / "pkg_one" / "pyproject.toml").read_text()
    (v1_dir / "pkg_one" / "pyproject.toml").write_text(pkg_one_pyproject.replace("<=1.25", "<=1.26.4"))
    poetry_run(v1_dir, "pkg_one", "lock --no-update")
    # This results in a lockfile with numpy==1.25 but pyproject.toml permits up to 1.26.5

    root_lock = (v1_dir / "poetry.lock").read_text()
    root_pyproject = (v1_dir / "pyproject.toml").read_text()
    assert envs.root_env.site_packages.find_distribution("numpy") is not None
    for env in envs.pkg_envs:
        assert env.site_packages.find_distribution("numpy") is None

    # Act
    result = poetry_run(v1_dir, "pkg_one", "update numpy")

    # Assert
    assert result.exit_code == 0
    assert "Updating numpy" in result.stdout
    assert "Skipping virtualenv creation" in result.stderr
    assert root_lock != (v1_dir / "poetry.lock").read_text()  # lock file is modified
    assert not (v1_dir / "pkg_one" / "poetry.lock").exists()  # pkg_one lockfile is not created
    assert root_pyproject == (v1_dir / "pyproject.toml").read_text()  # root pyproject.toml is not modified
    assert (v1_dir / "pkg_one" / "pyproject.toml").read_text().count("numpy") == 1
    assert envs.root_env.site_packages.find_distribution("numpy") is not None
    for env in envs.pkg_envs:
        assert env.site_packages.find_distribution("numpy") is None


def test_lock(repo_manager, poetry_run):
    # Arrange
    v1_dir = repo_manager.get_repo("v1", preinstalled=False)
    (v1_dir / "poetry.lock").unlink()
    root_pyproject = (v1_dir / "pyproject.toml").read_text()

    # Act
    result = poetry_run(v1_dir, "pkg_one", "lock")

    # Assert
    assert result.exit_code == 0
    assert "Writing lock file" in result.stdout
    assert (v1_dir / "poetry.lock").exists()  # lock file is created at root instead of pkg_one
    assert not (v1_dir / "pkg_one" / "poetry.lock").exists()  # pkg_one lockfile is not created
    assert root_pyproject == (v1_dir / "pyproject.toml").read_text()  # root pyproject.toml is not modified


def test_install(repo_manager, poetry_run):
    # Arrange
    v1_dir = repo_manager.get_repo("v1", preinstalled=False)
    envs_before = repo_manager.get_envs(v1_dir)

    root_lock = (v1_dir / "poetry.lock").read_text()
    root_pyproject = (v1_dir / "pyproject.toml").read_text()
    for env in [envs_before.root_env, *envs_before.pkg_envs]:
        assert env.is_venv() is False
        assert is_system_env(env)

    # Act
    result = poetry_run(v1_dir, "pkg_one", "install")

    # Assert
    assert result.exit_code == 0
    assert "Installing dependencies from lock file" in result.stdout
    assert root_lock == (v1_dir / "poetry.lock").read_text()  # lock file is not modified
    assert not (v1_dir / "pkg_one" / "poetry.lock").exists()  # pkg_one lockfile is not created
    assert root_pyproject == (v1_dir / "pyproject.toml").read_text()  # root pyproject.toml is not modified

    envs_after = repo_manager.get_envs(v1_dir)
    assert not is_system_env(envs_after.root_env)
    assert envs_after.root_env.is_venv() is True
    for env in envs_after.pkg_envs:
        assert env.is_venv() is False
        assert is_system_env(env)


def test_build(repo_manager, poetry_run):
    # Arrange
    v1_dir = repo_manager.get_repo("v1", preinstalled=False)

    # Act
    result = poetry_run(v1_dir, "pkg_three", "build")

    # Assert
    assert result.exit_code == 0
    assert "Building pkg-three" in result.stdout

    tarfile_path = next((v1_dir / "pkg_three" / "dist").glob("*.tar.gz"))
    with tarfile.open(tarfile_path, "r:gz") as tar:
        tar.extractall(path=v1_dir / "pkg_three" / "dist")
    pkg_info_path = next((v1_dir / "pkg_three" / "dist").rglob("PKG-INFO"))
    # Ensure extras are included
    assert "Requires-Dist: pkg-two[withpandas] (==0.1.0)" in pkg_info_path.read_text()
