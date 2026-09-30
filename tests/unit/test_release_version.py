import pytest

from scripts.next_release_version import (
    StableVersion,
    latest_stable_version,
    release_version,
)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("major", "v1.0.0"),
        ("minor", "v0.4.0"),
        ("patch", "v0.3.1"),
    ],
)
def test_release_version_bumps_latest_stable_tag(kind, expected):
    actual = release_version(
        kind,
        tags=["v0.2.0", "v0.3.0", "v0.4.0-rc1", "unrelated"],
    )

    assert actual.tag == expected


def test_release_version_uses_explicit_resume_tag_without_bumping():
    actual = release_version("major", resume_tag="v0.3.1", tags=["v0.3.0"])

    assert actual == StableVersion(0, 3, 1)


def test_latest_stable_version_defaults_for_repository_without_tags():
    assert latest_stable_version(["preview", "v1.0.0-rc1"]).tag == "v0.0.0"


@pytest.mark.parametrize("value", ["0.3", "v0.3", "v0.3.0-rc1", "release-1"])
def test_stable_version_rejects_non_release_tags(value):
    with pytest.raises(ValueError, match="expected vMAJOR.MINOR.PATCH"):
        StableVersion.parse(value)
