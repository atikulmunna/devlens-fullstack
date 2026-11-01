"""How serious a security-sensitive change is, from the categories the diff scan gave it.

Pure and standard-library only: the commit-diff API and the PR risk Action (pr-risk/) both use it.
"""

# Secrets and keys are exposed the moment they land; removing an auth or token check is as serious.
HIGH_RISK = {"secret", "credential", "password", "api_key"}
MEDIUM_RISK = {"auth", "token", "jwt", "oauth", "crypto"}


def flag_severity(categories: list[str]) -> str:
    plain = {category.removeprefix("removed: ") for category in categories}
    removed = {category.removeprefix("removed: ") for category in categories if category.startswith("removed: ")}
    if plain & HIGH_RISK or removed & MEDIUM_RISK:
        return "high"
    if plain & MEDIUM_RISK:
        return "medium"
    return "low"


def with_severity(flags: list[dict]) -> list[dict]:
    return [{**flag, "severity": flag_severity(flag.get("categories") or [])} for flag in flags]
