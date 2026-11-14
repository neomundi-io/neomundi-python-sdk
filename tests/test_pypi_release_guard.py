"""Publishing preparation remains non-activating until a separate approved release.

Deliberately Python 3.9-compatible, offline, and independent of PyYAML.
These guards cannot replace a review of GitHub branch/environment rules.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pypi_upload_remains_blocked_in_candidate_metadata():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"Private :: Do Not Upload"' in pyproject
    assert 'name = "neomundi"' in pyproject
    assert 'version = "2.0.0"' in pyproject


def test_publication_workflow_is_explicit_manual_only():
    yml = (ROOT / ".github/workflows/publish-pypi.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in yml
    # No other event trigger. Documented trigger is an explicit manual dispatch.
    event_block = yml.split("on:", 1)[1].split("\npermissions:", 1)[0]
    assert "push:" not in event_block
    assert "pull_request:" not in event_block
    assert "release:" not in event_block
    assert "schedule:" not in event_block
    assert "workflow_dispatch:" in event_block


def test_publication_requires_named_tag_confirmation_and_environment():
    yml = (ROOT / ".github/workflows/publish-pypi.yml").read_text(encoding="utf-8")
    assert "github.ref == 'refs/heads/main'" in yml
    assert "inputs.confirmation == 'PUBLISH_NEOMUNDI_TO_PYPI'" in yml
    assert "inputs.tag == 'sdk-v2.0.0'" in yml
    assert '"Private :: Do Not Upload" not in config' in yml
    assert "current == head" in yml
    assert "name: pypi" in yml
    assert "id-token: write" in yml
    assert "pypa/gh-action-pypi-publish@release/v1" in yml
    assert "PYPI_TOKEN" not in yml
    assert "password:" not in yml
