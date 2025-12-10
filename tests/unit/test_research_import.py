"""Import checks for the research tools module."""

import importlib


def test_research_module_import() -> None:
    """Ensure the research tools module imports without syntax errors."""
    module = importlib.import_module("app.tools.research")

    assert hasattr(module, "check_api_status")
    assert hasattr(module, "run_research_pipeline")
