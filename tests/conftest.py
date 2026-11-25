import pytest

from churnlab.config import RESULTS_DIR


@pytest.fixture(scope="session", autouse=True)
def results():
    if not (RESULTS_DIR / "retention.json").exists():
        from churnlab import pipeline
        pipeline.main()
