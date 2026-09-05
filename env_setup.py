"""Small helper for reading/writing .env without extra dependencies."""
import os

ENV_PATH = ".env"


def read_env() -> dict:
    values = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip()
    return values


def write_env(updates: dict):
    """Merges `updates` into the existing .env, preserving other lines/comments."""
    lines = []
    seen = set()
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                stripped = line.rstrip("\n")
                if "=" in stripped and not stripped.strip().startswith("#"):
                    key = stripped.split("=", 1)[0].strip()
                    if key in updates:
                        lines.append(f"{key}={updates[key]}\n")
                        seen.add(key)
                        continue
                lines.append(line if line.endswith("\n") else line + "\n")

    for key, val in updates.items():
        if key not in seen:
            lines.append(f"{key}={val}\n")

    with open(ENV_PATH, "w") as f:
        f.writelines(lines)


def reload_config():
    """Re-reads .env and refreshes the config module's values in-place."""
    import importlib
    from dotenv import load_dotenv
    load_dotenv(override=True)
    import config
    importlib.reload(config)
    return config
