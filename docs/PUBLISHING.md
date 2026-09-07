# Publish this source release

Publication is separate from running the app. The app never needs a GitHub account or API key.
This source package contains a local Git repository and a `v0.1.0` release tag.
No remote repository was created by the build environment.

## Before publishing

Install Git and GitHub CLI from their official distributions. Log in through GitHub CLI:

```sh
gh auth login --hostname github.com --web --scopes repo,workflow
```

The workflow scope permits publishing the included GitHub Actions file. No token is copied into the app.
The publisher defaults to the personal account `danial-maqbool`. It checks the current CLI account before writing.
Use `--owner YOUR-ACCOUNT` only when publishing your own copy to that same logged-in personal account.

## Check, then publish

Run these commands in this repository:

```sh
python scripts/publish.py --dry-run
python scripts/publish.py --check
python scripts/publish.py
```

`--dry-run` checks the local Git state without network calls.
`--check` also checks account identity and existing repository visibility. It does not create or push anything.
The last command creates the public repository when it is absent, pushes `main` and `v0.1.0`, sets the description and topics, and verifies the remote commit.

The combined five-project package also includes `publish_all.py`. Run it from that package to publish all five.

## Failure behavior

The publisher requires a clean local `main` branch and a version tag at the current release commit.
It refuses a mismatched origin, a private or archived repository, unrelated remote history, or a conflicting release tag.
It never force-pushes and does not change repository visibility.

A network or permission failure can leave an empty created repository or a partly completed publication.
Completed publications remain in place. Check the reported repository state and rerun after correcting the problem.
Compatible existing history can be resumed without replacing remote commits.

The build environment ran offline guard tests for the publisher. It did not execute a live GitHub publication.

## References

- GitHub CLI: https://cli.github.com/
- Repository creation: https://cli.github.com/manual/gh_repo_create
- Repository settings: https://cli.github.com/manual/gh_repo_edit
