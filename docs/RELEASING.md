# Releasing MLOX

MLOX releases are created by the **Deploy Release** GitHub Actions workflow.
The workflow calculates a stable semantic version from the latest `vX.Y.Z` tag,
validates and builds the selected commit, publishes the exact artifacts to PyPI,
verifies the installed package, creates the GitHub Release, and deploys the
website, API documentation, and wiki from the release tag.

## One-time repository setup

The repository owner must complete these settings before the first automated
release:

1. In GitHub, create an environment named `pypi`.
2. Add required reviewers to that environment so tag creation and package
   publication require an explicit approval.
3. In the PyPI settings for `busysloths-mlox`, add a GitHub Trusted Publisher:
   - owner: `BusySloths`
   - repository: `mlox`
   - workflow: `deploy-release.yml`
   - environment: `pypi`
4. Remove the obsolete `PYPI_API_TOKEN` repository secret after Trusted
   Publishing has succeeded once.
5. Protect `main` and release tags according to the repository access policy.

The publisher uses short-lived OpenID Connect credentials. No PyPI password or
API token is stored in the workflow.

## Deploy a release

1. Confirm release-blocking work is merged into `main` and checks are green.
2. Open **Actions → Deploy Release → Run workflow**.
3. Select `patch`, `minor`, or `major` and run it from `main`.
4. Review the calculated version and validation jobs.
5. Approve the `pypi` environment deployment.
6. Confirm the PyPI verification matrix, GitHub Release, and docs deployment
   complete successfully.

For example, when the latest tag is `v0.3.0`, the choices produce:

| Choice | New tag |
| --- | --- |
| `patch` | `v0.3.1` |
| `minor` | `v0.4.0` |
| `major` | `v1.0.0` |

The release contains generated notes, the wheel, source distribution, and a
`SHA256SUMS` file. The website links to the new release, API docs are built from
the released source, and the checked-in `wiki/` directory is synchronized.

## Failure and recovery

Validation and build failures occur before the protected release job and can be
fixed normally on `main`. PyPI versions and Git tags are immutable, so never
delete or move a release tag to retry publication.

If the workflow fails after creating the tag, dispatch **Deploy Release** again
from `main` and set `resume_tag` to that exact `vX.Y.Z` tag. The workflow then:

- rebuilds the tagged commit rather than current `main`;
- verifies that the tag still points to the expected commit;
- allows already-uploaded PyPI files while publishing anything missing; and
- refuses recovery when the GitHub Release is already published.

If only documentation deployment fails after the GitHub Release is published,
run **Deploy Docs** manually with the release tag. Do not run another package
release.

## Release content policy

GitHub Releases are the canonical release history. Pull-request labels organize
the generated notes according to `.github/release.yml`. User-visible breaking
changes, migration instructions, known limitations, and security notes still
require deliberate prose in the relevant pull request or a manually prepared
release note.

The wiki is documentation, not a second changelog. The website displays the
latest release and links back to the canonical GitHub Release.
