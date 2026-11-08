import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_alembic_refuses_dotenv_target_without_process_database_url(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    shutil.copy2(project_root / "alembic.ini", tmp_path / "alembic.ini")
    shutil.copytree(project_root / "migrations", tmp_path / "migrations")
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql+psycopg://pytest:pytest@127.0.0.1:1/eduflow_test\n"
        "SECRET_KEY=pytest-only-secret-key\n",
        encoding="utf-8",
    )

    child_env = os.environ.copy()
    child_env.pop("DATABASE_URL", None)
    child_env.pop("TEST_DATABASE_URL", None)
    result = subprocess.run(
        [
            sys.executable, "-m", "alembic", "-c",
            str(tmp_path / "alembic.ini"), "current",
        ],
        cwd=tmp_path,
        env=child_env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert "DATABASE_URL is required for Alembic" in result.stderr
    assert "connection refused" not in result.stderr.lower()
