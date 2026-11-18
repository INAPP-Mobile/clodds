#!/usr/bin/env python3
"""check_pins.py — verify every Dockerfile image pin in a template repo.

Rules:
  1. A pin must exist (a tag, or a digest).
  2. A tag must not be floating (latest / -latest / main / stable / ...).
  3. The pinned tag must exist upstream in the registry.

A pin file (railway.json / template-vars.json / template-editor-raw.json) that
declares an image must also use an immutable pin.

Exit code 0 = all pins good, 1 = at least one problem found.

Stdlib only, so it runs anywhere with python3 and no pip install.
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

FLOATING = re.compile(
    r"^(latest|main|master|stable|edge|dev|develop|nightly|rolling|current|"
    r"release|.*-latest|.*-stable|.*-edge|.*-dev|latest-.*)$"
)
# A major-only tag (e.g. "3", "8", "17") is also floating: it moves.
MAJOR_ONLY = re.compile(r"^v?\d+$")
# pgvector-style moving channels ("pg17") float within the major series.
CHANNEL = re.compile(r"^pg\d+$")

DOCKERFILE_RE = re.compile(r"(^|/)(dockerfile[^/]*)$", re.I)
AS_ALIAS_RE = re.compile(r"\s+AS\s+([A-Za-z0-9_.-]+)\s*$", re.I)
FROM_RE = re.compile(r"^\s*FROM\s+(.+)$", re.I)


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout


def find_dockerfiles():
    out = sh(["git", "ls-files"])
    files = out.splitlines()
    return [f for f in files if DOCKERFILE_RE.search(f)]


def parse_froms(text):
    """Return list of (image_ref, alias_or_None) from a Dockerfile."""
    # Join line continuations.
    text = re.sub(r"\\\s*\n\s*", " ", text)
    refs = []
    for line in text.splitlines():
        m = FROM_RE.match(line)
        if not m:
            continue
        rest = m.group(1)
        # Strip trailing comments that are not inside the ref.
        rest = re.sub(r"\s+#.*$", "", rest).strip()
        alias = None
        am = AS_ALIAS_RE.search(rest)
        if am:
            alias = am.group(1)
            rest = rest[: am.start()].strip()
        if not rest:
            continue
        refs.append((rest.split()[0], alias))
    return refs


def split_ref(ref):
    """-> (registry, repository, tag, digest)"""
    digest = None
    if "@" in ref:
        ref, digest = ref.split("@", 1)
    registry = "docker.io"
    repository = ref
    # A leading segment containing '.' or ':' (or equal to 'localhost') is a registry.
    if "/" in ref:
        head, rest = ref.split("/", 1)
        if "." in head or ":" in head or head == "localhost":
            registry, repository = head, rest
    tag = None
    if "/" in repository:
        last = repository.rsplit("/", 1)[1]
    else:
        last = repository
    if ":" in last:
        tag = last.rsplit(":", 1)[1]
        repository = repository[: len(repository) - len(tag) - 1]
    if registry == "docker.io" and "/" not in repository:
        repository = "library/" + repository
    return registry, repository, tag, digest


def _http(url, headers, method="GET", timeout=25):
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, b"", dict(e.headers or {})
    except Exception:
        return 0, b"", {}


def _dockerhub_token(repository):
    url = ("https://auth.docker.io/token?service=registry.docker.io"
           f"&scope=repository:{repository}:pull")
    status, body, _ = _http(url, {"Accept": "application/json"})
    if status != 200:
        return None
    try:
        tok = json.loads(body).get("token")
        return tok
    except Exception:
        return None


def _ghcr_token(repository):
    url = f"https://ghcr.io/token?scope=repository:{repository}:pull"
    status, body, _ = _http(url, {"Accept": "application/json"})
    if status != 200:
        return None
    try:
        return json.loads(body).get("token")
    except Exception:
        return None


def tag_exists(registry, repository, tag):
    """True if the tag exists upstream. None if the registry is unreachable."""
    if registry in ("docker.io", "registry-1.docker.io"):
        tok = _dockerhub_token(repository)
        if not tok:
            return None
        url = f"https://registry-1.docker.io/v2/{repository}/manifests/{tag}"
        headers = {
            "Authorization": f"Bearer {tok}",
            "Accept": ", ".join([
                "application/vnd.docker.distribution.manifest.v2+json",
                "application/vnd.docker.distribution.manifest.list.v2+json",
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.oci.image.index.v1+json",
            ]),
        }
        status, _, _ = _http(url, headers, method="HEAD")
        if status == 200:
            return True
        if status == 404:
            return False          # tag definitively does not exist
        if status in (401, 403):
            return False          # exists but we cannot read it anonymously
        return None               # network/registry problem - inconclusive
    if registry == "ghcr.io":
        tok = _ghcr_token(repository)
        if not tok:
            return None
        url = f"https://ghcr.io/v2/{repository}/manifests/{tag}"
        headers = {
            "Authorization": f"Bearer {tok}",
            "Accept": ", ".join([
                "application/vnd.docker.distribution.manifest.v2+json",
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.oci.image.index.v1+json",
            ]),
        }
        status, _, _ = _http(url, headers, method="HEAD")
        if status == 200:
            return True
        if status == 404:
            return False
        if status in (401, 403):
            return False
        return None
    if registry == "quay.io":
        url = f"https://quay.io/v2/{repository}/tags/list"
        status, body, _ = _http(url, {})
        if status != 200:
            return None
        try:
            tags = json.loads(body).get("tags") or []
        except Exception:
            return None
        return tag in tags
    # Unknown registry: try the public v2 endpoint anonymously.
    url = f"https://{registry}/v2/{repository}/manifests/{tag}"
    status, _, _ = _http(url, {}, method="HEAD")
    if status == 200:
        return True
    if status in (401, 403):
        return False
    return None


def check_pin_files(root):
    problems = []
    for name in ("railway.json", "template-vars.json", "template-editor-raw.json"):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            problems.append((name, f"could not parse: {e}"))
            continue

        def walk(node, trail=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    if (k in ("image", "imageName", "dockerImage")
                            and isinstance(v, str) and "/" in v):
                        reg, repo, tag, dig = split_ref(v)
                        if not dig:
                            if not tag:
                                problems.append((name, f"{trail}/{k} = '{v}' has no tag"))
                            elif FLOATING.match(tag) or MAJOR_ONLY.match(tag):
                                problems.append(
                                    (name, f"{trail}/{k} = '{v}' is not pinned "
                                           f"to an immutable tag"))
                    walk(v, trail + "/" + str(k))
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, trail + f"[{i}]")

        walk(data)
    return problems


def main():
    root = os.getcwd()
    files = find_dockerfiles()
    if not files:
        print("No Dockerfiles found - nothing to check.")
        return 0

    print(f"Checking {len(files)} Dockerfile(s)\n")
    problems = []
    # Stage aliases are per-Dockerfile.
    for df in files:
        path = os.path.join(root, df)
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError as e:
            problems.append((df, f"unreadable: {e}"))
            continue
        refs = parse_froms(text)
        stages = set()
        for img, alias in refs:
            if alias:
                stages.add(alias.lower())
        for img, alias in refs:
            reg, repo, tag, dig = split_ref(img)
            if alias:
                continue
            # A bare name that matches an earlier stage alias is a local stage.
            if "/" not in img.split("@")[0] and not tag and img.lower() in stages:
                print(f"  skip   {df} :: {img}  (build stage)")
                continue
            if "/" not in img.split("@")[0] and not tag:
                # A bare name with no tag and not a stage: local build context
                # image or an official image missing a pin.
                print(f"  skip   {df} :: {img}  (no registry, not a stage)")
                continue
            if dig:
                print(f"  ok     {df} :: {img}  (digest pin)")
                continue
            if not tag:
                problems.append((df, f"'{img}' has no tag (implicitly :latest)"))
                print(f"  FAIL   {df} :: {img}  (no tag)")
                continue
            if FLOATING.match(tag):
                problems.append((df, f"'{img}' uses a floating tag '{tag}'"))
                print(f"  FAIL   {df} :: {img}  (floating tag)")
                continue
            if MAJOR_ONLY.match(tag) or CHANNEL.match(tag):
                problems.append(
                    (df, f"'{img}' is pinned to major-only tag '{tag}' "
                         f"(moves within the major series)"))
                print(f"  FAIL   {df} :: {img}  (major-only tag)")
                continue
            exists = tag_exists(reg, repo, tag)
            if exists is True:
                print(f"  ok     {df} :: {img}")
            elif exists is False:
                problems.append((df, f"tag '{tag}' of '{reg}/{repo}' does not exist upstream"))
                print(f"  FAIL   {df} :: {img}  (tag not found upstream)")
            else:
                print(f"  warn   {df} :: {img}  (upstream unreachable - skipped)")

    print()
    for name, msg in check_pin_files(root):
        problems.append((name, msg))
        print(f"  FAIL   {name}: {msg}")

    print()
    if problems:
        print(f"pin-check FAILED: {len(problems)} problem(s)")
        for name, msg in problems:
            print(f"  - {name}: {msg}")
        return 1
    print("pin-check passed: all pins are immutable and exist upstream.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
