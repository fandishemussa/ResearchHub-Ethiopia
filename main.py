"""PyCharm-friendly development entrypoint for ResearchHub Ethiopia.

The production FastAPI application lives in ``backend/researchhub/main.py``.
This root-level file exists so opening the project in PyCharm and running
``main.py`` starts the API without needing to manually configure PYTHONPATH.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent

for package_dir in ("backend", "harvester", "ai"):
    path = str(PROJECT_ROOT / package_dir)
    if path not in sys.path:
        sys.path.insert(0, path)

from researchhub.main import app  # noqa: E402


def main() -> None:
    """Run the FastAPI development server."""

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8111,
        reload=True,
        reload_dirs=[
            str(PROJECT_ROOT / "backend"),
            str(PROJECT_ROOT / "harvester"),
            str(PROJECT_ROOT / "ai"),
        ],
    )


if __name__ == "__main__":
    main()
