"""Git repository scraper — reads recent commits and modified files via GitPython."""

import os
from pathlib import Path


def get_repo_commits(repo_path: str = None, limit: int = 10) -> list:
    """Return the last *limit* commits from the given git repository."""
    import git

    if repo_path is None:
        repo_path = os.getenv("GIT_REPO_PATH", ".")
    limit = int(os.getenv("MAX_COMMITS", str(limit)))

    try:
        repo = git.Repo(repo_path, search_parent_directories=True)
        commits = []
        for commit in repo.iter_commits(max_count=limit):
            commits.append(
                {
                    "hash": commit.hexsha[:8],
                    "author": str(commit.author),
                    "message": commit.message.strip().splitlines()[0],
                    "timestamp": float(commit.committed_date),
                    "repo_path": repo_path,
                }
            )
        return commits
    except Exception:
        return []


def get_modified_files(repo_path: str = None) -> list:
    """Return list of currently modified / untracked files in the repo."""
    import git

    if repo_path is None:
        repo_path = os.getenv("GIT_REPO_PATH", ".")

    try:
        repo = git.Repo(repo_path, search_parent_directories=True)
        modified = []

        # Unstaged changes
        for item in repo.index.diff(None):
            modified.append(item.a_path)
        # Staged changes
        try:
            for item in repo.index.diff("HEAD"):
                modified.append(item.a_path)
        except Exception:
            pass
        # Untracked
        modified.extend(repo.untracked_files)

        return list(set(modified))
    except Exception:
        return []
