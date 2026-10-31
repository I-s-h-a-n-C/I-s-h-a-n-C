#!/usr/bin/env python3
"""Refresh the SVG profile's public GitHub statistics.

The workflow uses the built-in GITHUB_TOKEN. No personal access token,
external Python dependencies, or extra GitHub secrets are required.
"""
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import json
import os
import re
import sys
from urllib.request import Request, urlopen

LOGIN = "I-s-h-a-n-C"
ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("repo_data", "stars_data", "contrib_data",
          "followers_data", "commits_data", "updated_data")



def github_graphql(query: str, variables: dict) -> dict:
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN is missing")
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "I-s-h-a-n-C-profile-updater",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def github_stats() -> dict:
    """All repository totals refer to public repositories owned by LOGIN.

    GitHub's contributionsCollection returns activity within the previous
    twelve months; its commit count is contribution-eligible commits.
    """
    query = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        followers { totalCount }
        contributionsCollection {
          contributionCalendar { totalContributions }
          totalCommitContributions
        }
        repositories(first: 100, after: $cursor,
                     ownerAffiliations: OWNER, privacy: PUBLIC) {
          totalCount
          nodes { stargazerCount }
          pageInfo { hasNextPage endCursor }
        }
      }
    }"""
    cursor = None
    total_stars = 0
    results = {}
    while True:
        user = github_graphql(query, {"login": LOGIN, "cursor": cursor})["user"]
        if user is None:
            raise RuntimeError(f"GitHub account {LOGIN} was not found")
        repos = user["repositories"]
        total_stars += sum(node["stargazerCount"] for node in repos["nodes"])
        results["repo_data"] = repos["totalCount"]
        results["followers_data"] = user["followers"]["totalCount"]
        collection = user["contributionsCollection"]
        results["contrib_data"] = collection["contributionCalendar"]["totalContributions"]
        results["commits_data"] = collection["totalCommitContributions"]
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]
    results["stars_data"] = total_stars
    return {key: f"{value:,}" for key, value in results.items()}


def update_svg(path: Path, values: dict) -> bool:
    content = path.read_text(encoding="utf-8")
    original = content
    for field, value in values.items():
        if field not in FIELDS:
            continue
        pattern = rf'(<tspan id="{field}" class="value">)[^<]*(</tspan>)'
        content, count = re.subn(
            pattern, lambda match: match.group(1) + escape(str(value))
            + match.group(2), content
        )
        if count != 1:
            raise RuntimeError(f"Expected exactly one {field} in {path.name}, found {count}")
    if content != original:
        path.write_text(content, encoding="utf-8")
        return True
    return False


def main() -> None:
    today = datetime.now(timezone.utc).date()
    values = {}
    try:
        values.update(github_stats())
        values["updated_data"] = today.isoformat()
    except Exception as error:
        print(f"Could not fetch GitHub stats; preserving existing counts: {error}",
              file=sys.stderr)
    for filename in ("light_mode.svg", "dark_mode.svg"):
        changed = update_svg(ROOT / filename, values)
        print(f"{filename}: {'updated' if changed else 'no changes'}")


if __name__ == "__main__":
    main()
