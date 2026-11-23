# Copyright (C) 2025 Clyso
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Multi-cluster connections for otto, modelled on kubectl's kubeconfig."""

import argparse
import atexit
import contextlib
import copy
import datetime
import errno
import fcntl
import itertools
import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

DEFAULT_CONFIG = "~/.config/otto/config"
# Like kubeconfig: files say which format they use, so a future otto can
# migrate them and an older otto refuses a newer file instead of misreading it.
API_VERSION = "otto/v1"
KIND = "Config"
SECTIONS = ("clusters", "credentials", "connections")
CURRENT = "current-connection"
OUTPUTS = ("table", "json", "yaml", "name")
LOCK_TIMEOUT_S = 10.0
PROBE_TIMEOUT_S = 20
TIERS = ("read-only", "read-write", "admin")
_RANK = {"read-only": 0, "read-write": 1, "admin": 2}

# Always applied with fullmatch(): `$` alone would also accept a trailing newline.
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")
ENTITY_RE = re.compile(r"(client|mon|osd|mds|mgr)\.[A-Za-z0-9._-]+")
FSID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# NAME is the cluster's own name. It lives in the mon KV store, so everyone who
# connects sees the same one. ALIAS is a nickname on this machine only.
# Lowercase only, so the same name is never written two ways.
NAME_KEY = "otto/cluster_name"
CLUSTER_NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,62}")
NAME_READ_CAP = 'allow command "config-key get" with key prefix otto/'
NAME_WRITE_CAP = 'allow command "config-key set" with key prefix otto/'
NOT_SET = "not set"

_FIELDS = {
    "clusters": {"conf": str, "fsid": (str, type(None)), "name": (str, type(None))},
    "credentials": {"keyring": str, "entity": str},
    "connections": {
        "cluster": str,
        "credential": str,
        "tags": list,
        "expect_tier": (str, type(None)),
        "inspect_with": (str, type(None)),
        "verified": dict,
    },
}
_FORMATS = {
    ("clusters", "name"): CLUSTER_NAME_RE,
    ("clusters", "fsid"): FSID_RE,
    ("credentials", "entity"): ENTITY_RE,
}
_REQUIRED = {
    "clusters": ("conf",),
    "credentials": ("keyring", "entity"),
    "connections": ("cluster", "credential"),
}
# The result of the last live check, as _verified_block() writes it. Any field may
# be missing in a hand-written file; present ones must have these types.
_VERIFIED_FIELDS = {
    "at": str,
    "fsid": str,
    "caps": (dict, type(None)),
    "tier": str,
    "inspected_by": (str, type(None)),
    "conf": str,
    "keyring": str,
    "entity": str,
}


def _by_tier(**names: str) -> dict[str, str]:
    """read_only="a b" -> {"a": "read-only", "b": "read-only"}"""
    return {n: tier.replace("_", "-") for tier, ns in names.items() for n in ns.split()}


# Grants derived from src/mon/MonCap.cc and src/osd/OSDCap.cc profile expansion,
# read in Ceph main at 089e2b4 (2026-09-23, release 21) and checked live against
# Tentacle 20.2.4. A profile or grant not listed here stays "unknown", never
# read-only, so a newer Ceph can only make otto more careful, not less.
# Profiles that read the mon KV store outside otto/ (it holds secret keys) or
# create keys count as admin, like the equivalent explicit grants below.
MON_PROFILES = _by_tier(
    read_only="read-only fs-client simple-rados-client crash",
    read_write="read-write osd mds rbd simple-rados-client-with-blocklist",
    admin="mon mgr role-definer bootstrap-osd bootstrap-mds bootstrap-mgr "
    "bootstrap-rgw bootstrap-rbd bootstrap-rbd-mirror "
    "cephfs-mirror rbd-mirror rbd-mirror-peer rgw",
)
OSD_PROFILES = _by_tier(
    read_only="read-only", read_write="read-write rbd rbd-read-only rgw"
)
_PROFILE_NOTES = {
    ("mon", "mgr"): "can create/modify keys (auth rwx)",
    ("mon", "role-definer"): "has ALL caps on the auth subsystem (can mint keys)",
    ("mon", "bootstrap-osd"): "can create OSD keys (osd new)",
    ("mon", "cephfs-mirror"): "can read mirror peer keys (config-key cephfs/...)",
    ("mon", "rbd-mirror"): "can read mirror peer keys (config-key rbd/mirror/)",
    ("mon", "rbd-mirror-peer"): "can read and write mirror peer keys (config-key)",
    ("mon", "rgw"): "can read RGW secrets such as TLS keys (config-key)",
    ("osd", "rbd-read-only"): "permits rbd child_attach/child_detach class writes",
}


class OttoConfigError(Exception):
    pass


class ProbeError(Exception):
    """A live probe failed. `kind` says why, so the message can name the real cause:
    unreachable (no monitor answered), denied (the login was refused),
    no_mons (the conf names no monitors), or other."""

    def __init__(self, msg: str, kind: str = "other"):
        super().__init__(msg)
        self.kind = kind


def _fail(msg: str, code: int = 1):
    sys.stdout.flush()  # keep progress lines before the error when output is piped
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def _warn(msg: str) -> None:
    sys.stdout.flush()
    print(f"warning: {msg}", file=sys.stderr)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- config files: loading, merging, locking, atomic writes ----


def config_paths() -> list[Path]:
    env = os.environ.get("OTTO_CONFIG") or ""
    raw = [p for p in env.split(os.pathsep) if p] or [DEFAULT_CONFIG]
    return [Path(os.path.expanduser(p)).absolute() for p in raw]


def _empty_doc() -> dict:
    return {s: {} for s in SECTIONS}


def _validate_doc(data, path) -> dict:
    if data is None:
        return _empty_doc()
    if not isinstance(data, dict):
        raise OttoConfigError(f"{path}: top level must be a mapping")
    unknown = set(data) - set(SECTIONS) - {CURRENT, "apiVersion", "kind"}
    if unknown:
        raise OttoConfigError(
            f"{path}: unknown top-level key(s): {', '.join(sorted(map(str, unknown)))}"
        )
    # a hand-written file may leave apiVersion out
    version = data.get("apiVersion", API_VERSION)
    if version != API_VERSION:
        raise OttoConfigError(
            f"{path}: apiVersion {version!r} is not supported by this otto "
            f"(it reads {API_VERSION}); upgrade otto"
        )
    if data.get("kind", KIND) != KIND:
        raise OttoConfigError(f"{path}: kind must be '{KIND}'")
    for section in SECTIONS:
        entries = data.get(section)
        if entries is None:
            entries = {}
        if not isinstance(entries, dict):
            raise OttoConfigError(f"{path}: '{section}' must be a mapping")
        for name, entry in entries.items():
            if not isinstance(name, str) or not NAME_RE.fullmatch(name):
                raise OttoConfigError(f"{path}: invalid {section} name {name!r}")
            if not isinstance(entry, dict):
                raise OttoConfigError(f"{path}: {section}.{name} must be a mapping")
            for field in _REQUIRED[section]:
                if field not in entry:
                    raise OttoConfigError(
                        f"{path}: {section}.{name} is missing '{field}'"
                    )
            for field, value in entry.items():
                expected = _FIELDS[section].get(field)
                if expected is None:
                    raise OttoConfigError(
                        f"{path}: {section}.{name} has unknown field '{field}'"
                    )
                if not isinstance(value, expected):
                    raise OttoConfigError(
                        f"{path}: {section}.{name}.{field} has the wrong type"
                    )
                # these values reach shell completion and ceph arguments
                pattern = _FORMATS.get((section, field))
                if pattern and isinstance(value, str) and not pattern.fullmatch(value):
                    raise OttoConfigError(
                        f"{path}: {section}.{name}.{field} has an invalid value "
                        f"{value[:70]!r}"
                    )
            if section == "connections":
                _check_connection_values(f"{path}: connections.{name}", entry)
        data[section] = entries
    current = data.get(CURRENT)
    if current is not None and not isinstance(current, str):
        raise OttoConfigError(f"{path}: '{CURRENT}' must be a string")
    return data


def _check_connection_values(where: str, entry: dict) -> None:
    """The values inside a connection that listings and checks rely on."""
    tags = entry.get("tags", [])
    if not all(isinstance(t, str) and NAME_RE.fullmatch(t) for t in tags):
        raise OttoConfigError(f"{where}.tags must be a list of names")
    if entry.get("expect_tier") not in (None, *TIERS):
        raise OttoConfigError(f"{where}.expect_tier must be one of {', '.join(TIERS)}")
    verified = entry.get("verified") or {}
    for field, value in verified.items():
        expected = _VERIFIED_FIELDS.get(field)
        if expected is None:
            raise OttoConfigError(f"{where}.verified has unknown field '{field}'")
        if not isinstance(value, expected):
            raise OttoConfigError(f"{where}.verified.{field} has the wrong type")
    if verified.get("tier") not in (None, *TIERS, "unknown"):
        raise OttoConfigError(f"{where}.verified.tier is not a known tier")
    caps = verified.get("caps") or {}
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in caps.items()):
        raise OttoConfigError(f"{where}.verified.caps must map daemon names to strings")


def _read_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as e:
        raise OttoConfigError(f"cannot read {path}: {e}") from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise OttoConfigError(
            f"{path} is not valid YAML ({type(e).__name__}); fix or remove it"
        ) from None
    return _validate_doc(data, path)


class Config:
    """Merged view of every OTTO_CONFIG file; the first file to define an entry wins."""

    def __init__(self):
        self.paths = config_paths()
        self.docs = {p: _read_file(p) for p in self.paths}
        self.merged = _empty_doc()
        self.origin: dict = {s: {} for s in SECTIONS}
        self.current = None
        self.current_origin = None
        for p in self.paths:
            doc = self.docs[p]
            if doc is None:
                continue
            for section in SECTIONS:
                for name, entry in doc[section].items():
                    if name not in self.merged[section]:
                        self.merged[section][name] = entry
                        self.origin[section][name] = p
            if self.current is None and doc.get(CURRENT):
                self.current = doc[CURRENT]
                self.current_origin = p

    def target_for(self, section: str, name: str | None = None) -> Path:
        # kubectl rule: modify where the stanza is defined; create in the first
        # existing file; if none exist, create the last file in the list.
        if section == CURRENT and self.current_origin is not None:
            return self.current_origin
        if section != CURRENT and name in self.origin[section]:
            return self.origin[section][name]
        for p in self.paths:
            if self.docs[p] is not None:
                return p
        return self.paths[-1]


def load_config() -> Config:
    try:
        return Config()
    except OttoConfigError as e:
        _fail(str(e))


@contextlib.contextmanager
def _locked(path: Path):
    real = Path(os.path.realpath(path))
    real.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = real.with_name(real.name + ".lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + LOCK_TIMEOUT_S
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise OttoConfigError(
                        f"timed out after {LOCK_TIMEOUT_S:g}s waiting for another otto "
                        f"process to finish writing {real}"
                    ) from None
                time.sleep(0.05)
        yield real
    finally:
        os.close(fd)


def _atomic_write(real: Path, doc: dict) -> None:
    body = {k: v for k, v in doc.items() if v not in (None, {})}
    body.update(apiVersion=API_VERSION, kind=KIND)
    text = yaml.safe_dump(body, sort_keys=True, default_flow_style=False)
    fd, tmp = tempfile.mkstemp(dir=real.parent, prefix=f".{real.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            with contextlib.suppress(FileNotFoundError):  # keep a shared file's mode
                os.fchmod(f.fileno(), stat.S_IMODE(os.stat(real).st_mode))
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, real)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    # The file is already replaced. A directory that cannot be fsynced (some
    # network filesystems) only weakens durability; it must not report a write
    # that happened as one that failed.
    with contextlib.suppress(OSError):
        dir_fd = os.open(real.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


def _sweep_temp_files(real: Path) -> None:
    # Temp files are only created while holding this file's lock, so any left over
    # now belong to a writer that was killed mid-write. Only ours: a sibling
    # file "config.team" makes ".config.team.XXXXXXXX.tmp" under its own lock.
    prefix = f".{real.name}."
    for stale in real.parent.iterdir():
        middle = stale.name[len(prefix) : -len(".tmp")]
        ours = stale.name.startswith(prefix) and stale.name.endswith(".tmp")
        if ours and middle and "." not in middle:
            with contextlib.suppress(FileNotFoundError):
                stale.unlink()


def transact_files(paths, mutate, check=()):
    """Lock every file in PATHS, re-read them, apply mutate({path: doc}), and
    replace each file whose document changed. Files in CHECK are only read (again,
    now, without a lock: a shared read-only file needs no lock file) and must not
    be changed by mutate.

    Locks are taken in one sorted order, so two otto processes never wait on each
    other. Nothing is written unless every changed document is still valid (a
    generated name that is too long is caught here, not by the next reader). Each
    file is replaced atomically; if a later one fails, the error names the files
    already written. mutate() must not do network I/O.
    """
    by_real: dict[Path, list[Path]] = {}
    for p in [*paths, *check]:
        by_real.setdefault(Path(os.path.realpath(p)), []).append(Path(p))
    locked = {Path(os.path.realpath(p)) for p in paths}
    with contextlib.ExitStack() as stack:
        docs_of: dict[Path, dict] = {}
        for real in sorted(by_real):
            if real in locked:
                stack.enter_context(_locked(real))
                _sweep_temp_files(real)
            docs_of[real] = _read_file(real) or _empty_doc()
        before = copy.deepcopy(docs_of)
        result = mutate({p: docs_of[real] for real, ps in by_real.items() for p in ps})
        changed = [real for real in sorted(docs_of) if docs_of[real] != before[real]]
        if any(real not in locked for real in changed):
            raise OttoConfigError("internal error: a file that was only read changed")
        for real in changed:
            _validate_doc(docs_of[real], real)
        written: list[Path] = []
        for real in changed:
            try:
                _atomic_write(real, docs_of[real])
            except OSError as e:
                if not written:
                    raise
                raise OttoConfigError(
                    f"saved {', '.join(map(str, written))} but could not write {real}: "
                    f"{e.strerror or e}; the change is only partly saved, so check "
                    "these files with: otto config view"
                ) from None
            written.append(real)
        return result


def transact(path: Path, mutate):
    """transact_files() for one file: mutate(doc)."""
    return transact_files([path], lambda docs: mutate(docs[Path(path)]))


def _transact_or_fail(paths, mutate, check=()):
    """transact_files(), or exit with the reason. PATHS: one path or several."""
    many = isinstance(paths, (list, tuple, set))
    try:
        if many:
            return transact_files(paths, mutate, check)
        return transact(paths, mutate)
    except OttoConfigError as e:
        _fail(str(e))
    except OSError as e:
        _fail(f"cannot write {e.filename or paths}: {e.strerror or e}")


# ---- validation helpers ----


def _check_name(kind: str, name: str) -> None:
    if not NAME_RE.fullmatch(name):
        _fail(
            f"invalid {kind} name {name!r}: use letters, digits, '.', '_' or '-', "
            "start with a letter or digit, at most 63 characters"
        )


def _check_entity(entity: str) -> None:
    if not ENTITY_RE.fullmatch(entity):
        _fail(f"invalid Ceph user {entity!r}: expected TYPE.ID such as client.admin")


def _check_path(kind: str, raw: str) -> str:
    path = os.path.abspath(os.path.expanduser(raw))
    if any(c.isspace() for c in path):
        _fail(
            f"{kind} path {path!r} contains whitespace; Ceph splits CEPH_ARGS on spaces "
            "without quoting, so it cannot be passed safely. Move or symlink it."
        )
    if not os.path.isfile(path):
        _fail(f"{kind} {path} does not exist or is not a regular file")
    if not os.access(path, os.R_OK):
        _fail(f"{kind} {path} is not readable by this user")
    return path


def _keyring_entities(path: str) -> dict[str, bool]:
    """Map each [section] in a keyring to whether it contains a key= line."""
    sections: dict[str, bool] = {}
    current = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith(("#", ";")):
                continue
            if s.startswith("[") and s.endswith("]"):
                current = s[1:-1].strip()
                sections.setdefault(current, False)
            elif (
                current is not None and "=" in s and s.split("=", 1)[0].strip() == "key"
            ):
                sections[current] = True
    return sections


# ---- live probes against a cluster ----


def _probe_env() -> dict:
    env = dict(os.environ)
    # The python ceph CLI appends CEPH_ARGS *after* explicit flags, so a stray
    # CEPH_ARGS in the caller's shell would silently override the probe target.
    for var in ("CEPH_ARGS", "CEPH_CONF", "CEPH_KEYRING"):
        env.pop(var, None)
    return env


def _last_error_line(stderr: str) -> str:
    lines = [
        ln.strip()
        for ln in stderr.splitlines()
        if ln.strip() and "dangerous and experimental features are enabled" not in ln
    ]
    return lines[-1] if lines else "no error output"


def _capture(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=False,
        env=_probe_env(),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
    )


def _run_ceph(
    conf: str, keyring: str, entity: str, argv: list[str]
) -> subprocess.CompletedProcess:
    exe = shutil.which("ceph")
    if exe is None:
        raise ProbeError("the `ceph` CLI is not on PATH")
    cmd = [exe, "--conf", conf, "--keyring", keyring, "--name", entity]
    cmd += ["--connect-timeout", str(PROBE_TIMEOUT_S), *argv]
    try:
        return _capture(cmd, PROBE_TIMEOUT_S + 10)
    except subprocess.TimeoutExpired:
        raise ProbeError(
            f"no answer within {PROBE_TIMEOUT_S}s", "unreachable"
        ) from None
    except OSError as e:
        raise ProbeError(f"could not run ceph: {e.strerror}") from None


def _connect_error_kind(returncode: int, stderr: str) -> str:
    """Sort a failed connect by cause, from what the ceph CLI prints:
    `timed out` / `[errno 13] RADOS permission denied` / `cannot identify monitors`."""
    text = stderr.lower()
    if returncode == errno.EACCES or "permission denied" in text:
        return "denied"
    if "cannot identify monitors" in text or "unable to get monitor info" in text:
        return "no_mons"
    if "timed out" in _last_error_line(stderr).lower():
        return "unreachable"
    return "other"


def probe_fsid(conf: str, keyring: str, entity: str) -> str:
    r = _run_ceph(conf, keyring, entity, ["fsid"])
    if r.returncode != 0:
        raise ProbeError(
            _last_error_line(r.stderr), _connect_error_kind(r.returncode, r.stderr)
        )
    fsid = r.stdout.strip()
    if not FSID_RE.fullmatch(fsid):
        raise ProbeError("cluster returned something that is not an fsid")
    return fsid


def _conf_lookup(conf: str, entity: str, option: str, how="--lookup") -> str | None:
    """Read one setting from a ceph.conf the way the ceph CLI would see it.
    --lookup: only what the file sets; --show-config-value: with Ceph's defaults."""
    exe = shutil.which("ceph-conf")
    if exe is None:
        return None
    try:
        r = _capture([exe, "-c", conf, "-n", entity, how, option], 10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = r.stdout.strip()
    return value if r.returncode == 0 and value else None


def _connect_failure(
    where: str,
    e: ProbeError,
    conf: str,
    snap: str,
    keyring: str,
    entity: str,
    pinned: str | None = None,
) -> str:
    """Explain a failed connect: what happened, then what to check."""
    if e.kind == "unreachable":
        lines = [f"no monitor answered within {PROBE_TIMEOUT_S}s"]
        mons = _conf_lookup(snap, entity, "mon_host")
        if mons:
            lines.append(f"monitors listed in {conf}: {mons}")
        lines.append(
            "hint: is the cluster running, and can this machine reach those addresses?"
        )
    elif e.kind == "denied":
        lines = [
            f"the cluster refused the login for {entity} (permission denied)",
            f"hint: check that {keyring} holds {entity}'s current key",
            f"      (on the cluster: ceph auth get {entity})",
        ]
        if pinned:
            # A conf now pointing at another cluster also fails here, before the
            # fsid can be compared, because that cluster does not know the key.
            lines.append(
                f"hint: or {conf} now points to a different cluster than the pinned "
                f"one ({pinned})"
            )
    elif e.kind == "no_mons":
        lines = [
            f"{conf} does not say where the monitors are",
            "hint: add a 'mon host = ...' line to its [global] section",
        ]
    else:
        lines = [str(e)]
    return f"could not connect to {where}\n  " + "\n  ".join(lines)


def _reach(prefix, where, conf, keyring, entity, *, code=2, pinned=None, snap=None):
    """Read the live fsid through a private snapshot of the conf; on failure exit
    explaining why. Returns (snapshot, fsid)."""
    try:
        snap = snap or _snapshot_conf(conf)
    except OSError as e:
        _fail(f"{prefix}cannot make a private copy of {conf}: {e.strerror or e}", code)
    try:
        return snap, probe_fsid(snap, keyring, entity)
    except ProbeError as e:
        why = _connect_failure(where, e, conf, snap, keyring, entity, pinned)
        _fail(prefix + why, code)


def probe_caps(conf: str, keyring: str, as_entity: str, target: str):
    """Return (caps, None) or (None, reason). Secret key material is discarded here."""
    try:
        r = _run_ceph(
            conf, keyring, as_entity, ["auth", "get", target, "--format", "json"]
        )
    except ProbeError as e:  # a timeout here is a missing answer, not a crash
        return None, str(e)
    if r.returncode == errno.EACCES:
        return None, f"{as_entity} is not allowed to run 'auth get'"
    if r.returncode != 0:
        return None, _last_error_line(r.stderr)
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None, "unexpected (non-JSON) output from 'auth get'"
    if not (isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict)):
        return None, "unexpected output shape from 'auth get'"
    entry = data[0]
    if entry.get("entity") != target:
        return None, "'auth get' returned a different entity"
    if "caps" not in entry:  # never guess: absent caps must not read as read-only
        return None, "'auth get' returned no caps field"
    # An empty map is a user with no caps: it can do nothing, so read-only holds.
    caps = entry["caps"]
    if not isinstance(caps, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in caps.items()
    ):
        return None, "unexpected caps format from 'auth get'"
    return dict(caps), None


def _read_key(conf: str, keyring: str, entity: str, key: str):
    """Return (value, "") or (None, why): unset, not readable, or invalid."""
    try:
        r = _run_ceph(conf, keyring, entity, ["config-key", "get", key])
    except ProbeError as e:
        return None, str(e)
    if r.returncode == errno.ENOENT:
        return None, NOT_SET
    if r.returncode == errno.EACCES:
        return None, f"{entity} may not read it (grant mon '{NAME_READ_CAP}')"
    if r.returncode != 0:
        return None, _last_error_line(r.stderr)
    value = r.stdout.strip()
    if not CLUSTER_NAME_RE.fullmatch(value):
        return None, f"stored value {value[:70]!r} is not a valid name; ignoring it"
    return value, ""


def probe_name(conf: str, keyring: str, entity: str) -> tuple[str | None, str]:
    """The cluster's own name, from the mon KV store."""
    return _read_key(conf, keyring, entity, NAME_KEY)


def write_name(
    conf: str, keyring: str, entity: str, name: str, overwrite: bool
) -> None:
    """Store the cluster's own name in the mon KV store and read it back."""
    current, why = probe_name(conf, keyring, entity)
    if current == name:
        return
    invalid = why.startswith("stored value")
    if current is None and why != NOT_SET and not invalid:
        _fail(f"cannot check the cluster's current name: {why}")
    if (invalid or current not in (None, name)) and not overwrite:
        existing = f"calls itself '{current}'" if current else "has an invalid name"
        _fail(f"the cluster already {existing}; nothing was changed")
    try:
        r = _run_ceph(conf, keyring, entity, ["config-key", "set", NAME_KEY, name])
    except ProbeError as e:
        _fail(f"could not write the name: {e}", 2)
    if r.returncode == errno.EACCES:
        _fail(
            f"{entity} may not write the name; use an admin login or grant "
            f"mon '{NAME_WRITE_CAP}'"
        )
    if r.returncode != 0:
        _fail(f"could not write the name: {_last_error_line(r.stderr)}")
    stored, why = _read_key(conf, keyring, entity, NAME_KEY)
    if stored != name:
        _fail(f"wrote '{name}' but read back {stored or why!r}; check the cluster")


# ---- capability classification ----


def _split_grants(capstr: str) -> list[str]:
    grants, buf, quote = [], [], None
    for ch in capstr:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in ",;":
            grants.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    grants.append("".join(buf).strip())
    return [g for g in grants if g]


def _perm_tier(daemon: str, perm: str):
    if perm in ("*", "all"):
        return "admin", f"{daemon} '{perm}' grants everything"
    if daemon == "osd" and perm in ("class-read",):
        return "read-only", None
    if daemon == "osd" and perm in ("class-write",):
        return "read-write", f"osd {perm} can modify objects"
    if not perm or any(c not in "rwxps" for c in perm):
        return None, None
    if daemon == "mon":
        if "x" in perm:
            return (
                "admin",
                "mon 'x' permits auth commands, which expose every secret key",
            )
        if "w" in perm:
            return "read-write", "mon 'w' can change cluster state"
        return ("read-only", None) if set(perm) <= {"r"} else (None, None)
    if daemon == "mds":
        if set(perm) <= {"r"}:
            return "read-only", None
        return "read-write", f"mds '{perm}' can modify the filesystem"
    if daemon in _CHANGES:
        if "w" in perm or "x" in perm:
            return "read-write", f"{daemon} '{perm}' {_CHANGES[daemon]}"
        return ("read-only", None) if set(perm) <= {"r"} else (None, None)
    return None, None


_CHANGES = {
    "osd": "can modify or execute on objects",
    "mgr": "can run mutating module commands",
}


# Words that start a match clause after the permissions: they only narrow
# where a grant applies (pool=a, path=/x, tag cephfs data=a, network 10.0.0.0/8).
_MATCH_WORDS = {
    "pool",
    "namespace",
    "object_prefix",
    "tag",
    "network",
    "path",
    "fsname",
    "uid",
    "gids",
    "root_squash",
}


def _is_perm(token: str) -> bool:
    if token in ("*", "all", "class-read", "class-write"):
        return True
    return bool(token) and all(ch in "rwxps" for ch in token)


_UNPROVEN = "may change state (commands are not provably read-only)"


def _otto_keys_only(restriction: list[str]) -> bool:
    """True if a MonCap 'with ...' clause limits the key argument to otto/ keys."""
    if restriction[:3] == ["with", "key", "prefix"] and len(restriction) == 4:
        return restriction[3].startswith("otto/")
    if len(restriction) == 2 and restriction[0] == "with":
        return restriction[1].startswith("key=otto/")
    return False


def _config_key_tier(daemon: str, cmd: str, restriction: list[str]):
    # The mon KV store also holds secrets (dashboard and cephadm keys), so
    # reading it is only harmless when limited to otto's own keys.
    action = cmd.split()[1:2]
    if _otto_keys_only(restriction):
        if action in (["get"], ["exists"]):
            return "read-only", None
        return "read-write", f"{daemon} command '{cmd}' can change otto's KV keys"
    if action in (["get"], ["dump"]):
        return "admin", f"{daemon} command '{cmd}' can read stored secret keys"
    return "read-write", f"{daemon} command '{cmd}' {_UNPROVEN}"


def _grant_tier(daemon: str, grant: str):
    try:
        tokens = shlex.split(grant)
    except ValueError:
        return None, f"unparseable grant {grant!r}"
    if tokens and tokens[0] == "allow" and len(tokens) > 1 and tokens[1] == "profile":
        tokens = tokens[1:]
    if not tokens:
        return None, "empty grant"
    if tokens[0] == "profile":
        if len(tokens) < 2:
            return None, "profile without a name"
        name = tokens[1]
        table = {"mon": MON_PROFILES, "osd": OSD_PROFILES}.get(daemon, {})
        tier = table.get(name)
        if tier is None:
            return None, f"{daemon} profile '{name}' is not recognised"
        note = _PROFILE_NOTES.get((daemon, name))
        return tier, (f"{daemon} profile '{name}' {note}" if note else None)
    if tokens[0] != "allow" or len(tokens) < 2:
        return None, f"unrecognised grant {grant!r}"
    rest = tokens[1:]
    if rest[0] == "command":
        cmd = rest[1] if len(rest) > 1 else ""
        if cmd.split()[:1] == ["auth"]:
            return "admin", f"{daemon} command '{cmd}' exposes or mints secret keys"
        if cmd.split()[:1] == ["config-key"]:
            return _config_key_tier(daemon, cmd, rest[2:])
        return "read-write", f"{daemon} command '{cmd}' {_UNPROVEN}"
    if rest[0] == "service":
        service = rest[1] if len(rest) > 1 else ""
        perm = rest[2] if len(rest) > 2 else ""
        if daemon == "mon" and service == "auth":
            return "admin", "mon service 'auth' exposes or mints secret keys"
        if daemon == "mon" and service == "config-key":
            # MonCap matches a service grant before its config-key exclusion
            return "admin", "mon service 'config-key' can read stored secret keys"
        tier, why = _perm_tier(daemon, perm)
        return tier, why or (None if tier else f"unrecognised perms in {grant!r}")
    if rest[0] == "class":
        return (
            "read-write",
            f"{daemon} class grant {grant!r} calls object class methods",
        )
    # "allow r class-write pool=a": every permission word counts, not only the
    # first, and an unknown word after them is not assumed to be harmless.
    perms = list(itertools.takewhile(_is_perm, rest))
    after = rest[len(perms) : len(perms) + 1]
    graded = [_perm_tier(daemon, perm) for perm in perms]
    if (
        not graded
        or any(tier is None for tier, _ in graded)
        or (after and after[0].split("=", 1)[0] not in _MATCH_WORDS)
    ):
        return None, f"unrecognised perms in {grant!r}"
    return max(graded, key=lambda g: _RANK[g[0]])


def classify_caps(caps: dict) -> tuple[str, list[str]]:
    """Return (tier, reasons). Anything not provably read-only is treated as elevated."""
    worst = "read-only"
    unknown = False
    reasons: list[str] = []
    for daemon, capstr in sorted(caps.items()):
        if daemon not in ("mon", "osd", "mds", "mgr"):
            unknown = True
            reasons.append(f"unknown cap type '{daemon}'")
            continue
        for grant in _split_grants(capstr):
            tier, why = _grant_tier(daemon, grant)
            if tier is None:
                unknown = True
                reasons.append(why or f"unrecognised grant {grant!r}")
                continue
            if why:
                reasons.append(why)
            if _RANK[tier] > _RANK[worst]:
                worst = tier
    if worst == "admin":
        return "admin", reasons
    if unknown:
        return "unknown", reasons
    return worst, reasons


# ---- conf snapshot (closes the conf-file-swap race between probe and use) ----


def _snapshot_conf(conf: str) -> str:
    base = tempfile.gettempdir()
    if any(c.isspace() for c in base):
        base = "/tmp"
    snap_dir = tempfile.mkdtemp(prefix="otto-", dir=base)
    atexit.register(shutil.rmtree, snap_dir, True)
    # same file name, so Ceph derives the same cluster name ($cluster) from it
    dst = os.path.join(snap_dir, os.path.basename(conf))
    with open(conf, "rb") as src:
        data = src.read()
    fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
    return dst


# ---- activation: resolve the selected connection and point every ceph call at it ----


def _resolve(cfg: Config, name: str):
    """The cluster and credential of an existing connection."""
    conn = cfg.merged["connections"][name]
    cluster = cfg.merged["clusters"].get(conn["cluster"])
    if cluster is None:
        _fail(f"connection '{name}' refers to missing cluster '{conn['cluster']}'")
    cred = cfg.merged["credentials"].get(conn["credential"])
    if cred is None:
        _fail(
            f"connection '{name}' refers to missing credential '{conn['credential']}'"
        )
    return conn, cluster, cred


def _pinned(cfg: Config, name: str):
    """Resolve a connection whose cluster has a pinned fsid, and check its files."""
    conn, cluster, cred = _resolve(cfg, name)
    if not cluster.get("fsid"):
        _fail(
            f"cluster '{conn['cluster']}' has no pinned fsid yet; run: otto config verify {name}"
        )
    conf = _check_path("conf", cluster["conf"])
    return conn, cluster, cred, conf, _check_path("keyring", cred["keyring"])


def _login(cfg: Config, conn: dict) -> str:
    """A login is named after its Ceph user: client.viewer -> viewer."""
    cred = cfg.merged["credentials"].get(conn["credential"]) or {}
    return cred.get("entity", "?").removeprefix("client.")


def _referencing(cfg: Config, field: str, value: str) -> list[str]:
    """The connections whose FIELD is VALUE, e.g. every login of one cluster."""
    return sorted(
        n for n, c in cfg.merged["connections"].items() if c.get(field) == value
    )


def _find_cluster(
    cfg: Config, target: str, see: str = "otto cluster ls"
) -> tuple[str | None, str]:
    """The cluster saved here as TARGET (its alias), or else the one whose own
    name is TARGET. Returns (key, "") or (None, why)."""
    clusters = cfg.merged["clusters"]
    if target in clusters:
        return target, ""
    keys = sorted(k for k, e in clusters.items() if e.get("name") == target)
    if not keys:
        return None, f"no cluster called '{target}' (see: {see})"
    if len(keys) > 1:
        return (
            None,
            f"several clusters are named '{target}' ({', '.join(keys)}); use an alias",
        )
    return keys[0], ""


def _lookup(cfg: Config, target: str) -> tuple[str | None, str]:
    """Find the connection for NAME, ALIAS, NAME/LOGIN, ALIAS/LOGIN or a
    connection's own name. Returns (connection, "") or (None, why).

    Anything ambiguous is refused rather than guessed: picking between a
    read-only and an admin login is the operator's call, not otto's.
    """
    conns = cfg.merged["connections"]
    if target in conns:
        return target, ""
    ref, _, login = target.partition("/")
    key, why = _find_cluster(cfg, ref)
    if key is None:
        return None, why
    mine = _referencing(cfg, "cluster", key)
    logins = sorted({_login(cfg, conns[n]) for n in mine})
    if login:
        mine = [n for n in mine if _login(cfg, conns[n]) == login]
    if len(mine) == 1:
        return mine[0], ""
    if not login and key in mine:
        return key, ""  # the login `otto config add` created first
    if not mine and not logins:
        return None, f"cluster '{key}' has no login yet (see: otto config add)"
    if not mine:
        return (
            None,
            f"cluster '{key}' has no login '{login}' (logins: {', '.join(logins)})",
        )
    if login:
        return None, f"several connections use login '{login}': {', '.join(mine)}"
    return (
        None,
        f"cluster '{key}' has several logins: pick one with {key}/{'|'.join(logins)}",
    )


def _label(cfg: Config, name: str) -> str:
    """What to type for a connection: its cluster, CLUSTER/LOGIN, or its own name."""
    conn = cfg.merged["connections"][name]
    for label in (conn["cluster"], f"{conn['cluster']}/{_login(cfg, conn)}"):
        if _lookup(cfg, label)[0] == name:
            return label
    return name


def resolve_connection(cfg: Config, target: str) -> str:
    name, why = _lookup(cfg, target)
    if name is None:
        _fail(why)
    label = _label(cfg, name)
    if target not in (name, label):
        print(f"using '{label}' for '{target}'", file=sys.stderr)
    return name


def selected_connection(flag: str | None, cfg: Config):
    """flag > OTTO_CONNECT > current-connection (same chain as kubectl --context)."""
    if flag is not None:
        if not flag:
            _fail("-C/--connect needs a connection name")
        return flag, "--connect"
    env = os.environ.get("OTTO_CONNECT")
    if env:
        return env, "OTTO_CONNECT"
    if cfg.current:
        return cfg.current, f"current-connection in {cfg.current_origin}"
    return None, None


def check_fsid(
    cfg: Config, name: str, source: str, allow_fsid_mismatch: bool, doing: str
) -> dict:
    """Ask the cluster of connection NAME for its fsid, live, and stop unless it
    is the pinned one. Returns the checked target: connection, conf, snap (the
    private conf copy), keyring, entity and the live fsid."""
    conn, cluster, cred, conf, keyring = _pinned(cfg, name)
    pinned = cluster["fsid"]
    if _outdated(conn, cred):
        _warn(
            f"credential '{conn['credential']}' changed since connection '{name}' was verified; run: otto config verify {name}"
        )
    snap, live = _reach(
        f"connection '{name}' ({source}): ",
        f"cluster '{conn['cluster']}'",
        conf,
        keyring,
        cred["entity"],
        pinned=pinned,
    )
    if live != pinned:
        msg = (
            f"connection '{name}' ({source}): the cluster at {conf} is not the one registered "
            f"as '{conn['cluster']}'\n  registered fsid: {pinned}\n  live fsid:       {live}"
        )
        if not allow_fsid_mismatch:
            _fail(
                msg + f"\nrefusing to {doing}. If this change is expected: "
                f"otto config set-cluster {conn['cluster']} --conf {conf} --reset-fsid "
                f"&& otto config verify {name}",
                2,
            )
        _warn(msg + "\n--allow-fsid-mismatch given: proceeding anyway")
    return {
        "connection": name,
        "conf": conf,
        "snap": snap,
        "keyring": keyring,
        "entity": cred["entity"],
        "fsid": live,
    }


# The target this process checked and pointed Ceph at; empty when none was.
_ACTIVE: dict = {}


def activate_selected_connection(
    flag: str | None, allow_fsid_mismatch: bool = False
) -> None:
    # set below only when this process checked a cluster, never inherited
    os.environ.pop("OTTO_ACTIVE_CONNECTION", None)
    _ACTIVE.clear()
    has_config = any(p.exists() for p in config_paths())
    if flag is None and not os.environ.get("OTTO_CONNECT") and not has_config:
        return
    cfg = load_config()
    name, source = selected_connection(flag, cfg)
    if name is None:
        return
    # `otto use` stores a connection name, never an alias. If it is gone, stop:
    # an alias with the same name may belong to a different cluster.
    if source.startswith(CURRENT) and name not in cfg.merged["connections"]:
        _fail(
            f"the current connection '{name}' no longer exists; "
            "pick one with: otto use NAME"
        )
    name = resolve_connection(cfg, name)
    target = check_fsid(cfg, name, source, allow_fsid_mismatch, "run")

    if os.environ.get("CEPH_ARGS"):
        # never print the old value: it may hold a key or a keyring path
        _warn(
            f"ignoring the CEPH_ARGS already set in this shell; connection '{name}' selects the target"
        )
    os.environ["CEPH_ARGS"] = (
        f"--conf {target['snap']} --keyring {target['keyring']} "
        f"--name {target['entity']}"
    )
    os.environ["CEPH_CONF"] = target["snap"]
    os.environ["CEPH_KEYRING"] = target["keyring"]
    os.environ["OTTO_ACTIVE_CONNECTION"] = name
    _ACTIVE.update(target)
    # atexit handlers (conf snapshot cleanup) only run on a normal interpreter exit.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(128 + signal.SIGTERM))


# ---- questions at the terminal ----


class _Cancelled(Exception):
    pass


class _Prompter:
    """Prompts in the gcloud/gh style: numbered choices, the default in brackets,
    Enter accepts it. Colour only on a terminal and never with NO_COLOR set
    (https://no-color.org). Ctrl+C or Ctrl+D raises _Cancelled."""

    def __init__(self, interactive: bool):
        self.interactive = interactive
        self.color = (
            sys.stdout.isatty()
            and "NO_COLOR" not in os.environ
            and os.environ.get("TERM") != "dumb"
        )
        utf8 = (sys.stdout.encoding or "").lower().replace("-", "") == "utf8"
        self.tick = "✓" if utf8 else "ok"

    def _c(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def bold(self, text: str) -> str:
        return self._c(text, "1")

    def dim(self, text: str) -> str:
        return self._c(text, "2")

    def say(self, msg: str = "") -> None:
        print(f"  {msg}" if msg else "", flush=True)

    def ok(self, msg: str) -> None:
        print(f"  {self._c(self.tick, '32')} {msg}", flush=True)

    def warn(self, msg: str) -> None:
        print(f"  {self._c('!', '33')} {msg}", flush=True)

    def _input(self, prompt: str) -> str:
        try:
            return input(prompt)
        except (KeyboardInterrupt, EOFError):
            print()
            raise _Cancelled from None

    def ask(self, question: str, check) -> str:
        """Ask until check(reply) finds no problem with the answer."""
        while True:
            reply = self._input(f"  {self._c('?', '36')} {question}: ").strip()
            problem = check(reply)
            if not problem:
                return reply
            self.warn(problem)

    def confirm(self, question: str, default: bool) -> bool:
        hint = self.dim("[Y/n]" if default else "[y/N]")
        while True:
            reply = self._input(f"  {self._c('?', '36')} {question} {hint} ").strip()
            if not reply:
                return default
            if reply.lower() in ("y", "yes"):
                return True
            if reply.lower() in ("n", "no"):
                return False
            self.warn("answer y or n")

    def choose(
        self, question: str, options: list[tuple[str, str]], default: int
    ) -> int:
        print(f"  {self._c('?', '36')} {question}")
        width = max(len(label) for label, _ in options)
        for i, (label, note) in enumerate(options, 1):
            print(f"      {self.bold(str(i))}) {label.ljust(width)}   {self.dim(note)}")
        valid = [str(i) for i in range(1, len(options) + 1)]
        while True:
            reply = self._input(f"    Choice {self.dim('[' + str(default) + ']')}: ")
            reply = reply.strip() or str(default)
            if reply in valid:
                return int(reply)
            self.warn(f"choose {' or '.join(valid)}")


def _on_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


@contextlib.contextmanager
def _cancellable():
    """Turn Ctrl+C, Ctrl+D or a final "no" into a clean exit 130."""
    try:
        yield
    except _Cancelled:
        print("  Cancelled. Nothing was changed.", file=sys.stderr)
        sys.exit(130)


# ---- otto config ... subcommands ----


def cmd_set_cluster(args) -> None:
    _check_name("cluster", args.name)
    conf = _check_path("conf", args.conf)
    cfg = load_config()

    def mutate(doc):
        entry = doc["clusters"].get(args.name)
        if entry is None:
            doc["clusters"][args.name] = {"conf": conf, "fsid": None}
            return "created"
        if entry.get("conf") != conf and entry.get("fsid") and not args.reset_fsid:
            _warn(
                f"cluster '{args.name}' keeps its pinned fsid {entry['fsid']}; if the new conf "
                "points at a different cluster, every connection will refuse to run until you "
                "pass --reset-fsid and re-verify"
            )
        entry["conf"] = conf
        if args.reset_fsid:
            entry["fsid"] = None
            entry.pop("name", None)
        return "updated"

    result = _transact_or_fail(cfg.target_for("clusters", args.name), mutate)
    print(f"cluster '{args.name}' {result} (conf {conf})")
    if args.reset_fsid:
        users = _referencing(cfg, "cluster", args.name)
        if users:
            print(f"fsid unpinned; re-pin with: otto config verify {users[0]}")
    else:
        print(
            "its fsid is pinned live by `otto config set-connection` / `otto config verify`"
        )


def cmd_set_credentials(args) -> None:
    _check_name("credential", args.name)
    _check_entity(args.entity)
    keyring = _check_path("keyring", args.keyring)
    try:
        entities = _keyring_entities(keyring)
    except OSError as e:
        _fail(f"cannot read keyring {keyring}: {e.strerror}")
    if args.entity not in entities:
        found = ", ".join(sorted(entities)) or "none"
        _fail(f"keyring {keyring} has no [{args.entity}] section (found: {found})")
    if not entities[args.entity]:
        _fail(f"keyring {keyring} section [{args.entity}] has no 'key =' line")
    mode = os.stat(keyring).st_mode
    if mode & 0o077:
        _warn(
            f"keyring {keyring} is accessible by group/others (mode {oct(mode & 0o777)}); consider chmod 600"
        )
    cfg = load_config()

    def mutate(doc):
        existed = args.name in doc["credentials"]
        doc["credentials"][args.name] = {"keyring": keyring, "entity": args.entity}
        return "updated" if existed else "created"

    result = _transact_or_fail(cfg.target_for("credentials", args.name), mutate)
    print(f"credential '{args.name}' {result} ({args.entity}, keyring {keyring})")
    users = _referencing(cfg, "credential", args.name)
    if result == "updated" and users:
        _warn(f"re-verify connections using it: {', '.join(users)}")


def _live_check(
    cfg: Config,
    cluster_name: str | None,
    cluster: dict,
    cred: dict,
    inspector_name: str | None,
):
    """Authenticate, read the live fsid, and read the credential's real caps.

    cluster_name is None for a cluster that is not in the config yet."""
    conf = _check_path("conf", cluster["conf"])
    keyring = _check_path("keyring", cred["keyring"])
    where = f"cluster '{cluster_name}'" if cluster_name else f"the cluster in {conf}"
    pinned = cluster.get("fsid")
    snap, fsid = _reach("", where, conf, keyring, cred["entity"], code=1, pinned=pinned)
    if pinned and pinned != fsid:
        _fail(
            f"cluster '{cluster_name}' is pinned to fsid {pinned} but {conf} now reaches {fsid}.\n"
            f"If that is expected: otto config set-cluster {cluster_name} --conf {conf} --reset-fsid",
            2,
        )
    caps, why = probe_caps(snap, keyring, cred["entity"], cred["entity"])
    inspected_by = cred["entity"] if caps is not None else None
    if caps is None and inspector_name:
        insp = cfg.merged["credentials"].get(inspector_name)
        if insp is None:
            _fail(f"no such credential '{inspector_name}' for --inspect-with")
        insp_keyring = _check_path("keyring", insp["keyring"])
        prefix = f"inspector {insp['entity']}: "
        _, insp_fsid = _reach(
            prefix, where, conf, insp_keyring, insp["entity"], code=1, snap=snap
        )
        if insp_fsid != fsid:
            _fail(
                f"inspector credential '{inspector_name}' reached a different cluster ({insp_fsid})"
            )
        caps, why2 = probe_caps(snap, insp_keyring, insp["entity"], cred["entity"])
        if caps is not None:
            inspected_by = insp["entity"]
        else:
            why = f"{why}; inspector: {why2}"
    if caps is None:
        tier, reasons = "unknown", [f"caps could not be read ({why})"]
    else:
        tier, reasons = classify_caps(caps)
    own, own_why = probe_name(snap, keyring, cred["entity"])
    return {
        "fsid": fsid,
        "name": own,
        "name_why": own_why,
        "snap": snap,
        "caps": caps,
        "tier": tier,
        "reasons": reasons,
        "inspected_by": inspected_by,
        "conf": cluster["conf"],
        "keyring": cred["keyring"],
        "entity": cred["entity"],
    }


def _print_check(result: dict) -> None:
    print(f"  fsid:  {result['fsid']}")
    if result["name"]:
        print(f"  name:  {result['name']}  (the cluster's own name, {NAME_KEY})")
    else:
        print(f"  name:  none ({result['name_why']})")
    if result["caps"] is None:
        print("  caps:  (could not be read)")
    else:
        for daemon, capstr in sorted(result["caps"].items()):
            print(f"  caps:  {daemon} = {capstr!r}")
        print(f"         read via {result['inspected_by']}")
    print(f"  tier:  {result['tier']}")
    for reason in result["reasons"]:
        print(f"         - {reason}")


_VERIFIED = ("fsid", "caps", "tier", "inspected_by", "conf", "keyring", "entity")


def _verified_block(result: dict) -> dict:
    return {"at": _now(), **{k: result[k] for k in _VERIFIED}}


def _connection_entry(
    cluster: str,
    credential: str,
    result: dict,
    *,
    tags=(),
    expect_tier: str | None = None,
    inspect_with: str | None = None,
) -> dict:
    """A connection as it is saved, verified by the live check RESULT."""
    return {
        "cluster": cluster,
        "credential": credential,
        "tags": sorted(set(tags)),
        "expect_tier": expect_tier,
        "inspect_with": inspect_with,
        "verified": _verified_block(result),
    }


def _outdated(conn: dict, cred: dict) -> bool:
    """True when the credential's keyring or user changed after the last check."""
    v = conn.get("verified") or {}
    return bool(v) and (v.get("keyring"), v.get("entity")) != (
        cred.get("keyring"),
        cred.get("entity"),
    )


def _ago(stamp: str | None) -> str:
    """'5m ago' for a timestamp written by _now(); the raw text if unreadable."""
    try:
        then = datetime.datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return stamp or "-"
    if then.tzinfo is None:
        then = then.replace(tzinfo=datetime.UTC)
    secs = (datetime.datetime.now(datetime.UTC) - then).total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{int(secs // size)}{unit} ago"
    return "just now"


def _stored(docs: dict, cfg: Config, section: str, name: str, seen: dict, fields):
    """The entry as stored now (under the lock) if FIELDS still hold what the live
    check used; otherwise stop, because saving would attach that check's result
    to something it never looked at."""
    path = cfg.origin[section].get(name)
    entry = docs[path][section].get(name) if path else None
    if entry is None or any(entry.get(f) != seen.get(f) for f in fields):
        raise OttoConfigError(
            f"{section[:-1]} '{name}' changed while it was being checked; "
            "nothing was saved, re-run"
        )
    return entry


def _changes_cluster(entry: dict, result: dict) -> bool:
    """Would _save_cluster_facts() change this cluster entry? If not, its file is
    only checked, never locked: it may be a shared file this user cannot write."""
    new_name = _name_known(result) and entry.get("name") != result["name"]
    return entry.get("fsid") != result["fsid"] or new_name


def _save_cluster_facts(entry: dict, result: dict, save: bool = True) -> None:
    """Pin the fsid on first use, and remember the cluster's own name for listings
    that do not go live. A login that may not read the name learns nothing, so it
    never erases a name another login saw. A fsid pinned meanwhile is fine if it
    is this one (another verify got there first); a different one stops."""
    if entry.get("fsid") not in (None, result["fsid"]):
        raise OttoConfigError(
            f"the cluster was pinned to {entry['fsid']} meanwhile; nothing was saved"
        )
    if save:
        entry["fsid"] = result["fsid"]
        if _name_known(result):
            entry["name"] = result["name"]


def _name_known(result: dict) -> bool:
    """Did the live check learn the cluster's own name, or that it has none?
    (Not when the login may not read it.)"""
    return bool(result["name"]) or result["name_why"] == NOT_SET


def _check_inspector(cfg: Config, name: str | None) -> None:
    if name and name not in cfg.merged["credentials"]:
        _fail(f"no such credential '{name}' for --inspect-with")


def cmd_set_connection(args) -> None:
    _check_name("connection", args.name)
    for tag in args.tag:
        _check_name("tag", tag)
    cfg = load_config()
    cluster = cfg.merged["clusters"].get(args.cluster)
    if cluster is None:
        _fail(f"no such cluster '{args.cluster}' (see: otto config get-clusters)")
    cred = cfg.merged["credentials"].get(args.credential)
    if cred is None:
        _fail(
            f"no such credential '{args.credential}' (see: otto config get-credentials)"
        )
    _check_inspector(cfg, args.inspect_with)

    print(f"checking {cred['entity']} against cluster '{args.cluster}' ...")
    result = _live_check(cfg, args.cluster, cluster, cred, args.inspect_with)
    _print_check(result)

    if args.expect_tier and result["tier"] != args.expect_tier:
        msg = f"expected tier '{args.expect_tier}' but the live caps classify as '{result['tier']}'"
        if not args.force:
            _fail(msg + "; nothing was registered (pass --force to register anyway)")
        _warn(msg + "; registering anyway because of --force")
    elif not args.expect_tier and result["tier"] == "unknown":
        _warn(
            "could not determine this credential's real permissions; pass --inspect-with <credential> to read them"
        )

    # One locked write: the cluster and credentials must still be what was checked.
    target = cfg.target_for("connections", args.name)
    creds = [args.credential] + ([args.inspect_with] if args.inspect_with else [])
    save = _changes_cluster(cluster, result)
    cluster_file = cfg.origin["clusters"][args.cluster]
    paths = [target, *([cluster_file] if save else [])]
    check = [cfg.origin["credentials"][c] for c in creds]
    check += [] if save else [cluster_file]

    def mutate(docs):
        entry = _stored(docs, cfg, "clusters", args.cluster, cluster, ("conf",))
        for c in creds:
            seen = cfg.merged["credentials"][c]
            _stored(docs, cfg, "credentials", c, seen, ("keyring", "entity"))
        _save_cluster_facts(entry, result, save)
        conns = docs[target]["connections"]
        existed = args.name in conns
        conns[args.name] = _connection_entry(
            args.cluster,
            args.credential,
            result,
            tags=args.tag,
            expect_tier=args.expect_tier,
            inspect_with=args.inspect_with,
        )
        return "updated" if existed else "created"

    outcome = _transact_or_fail(paths, mutate, check)
    print(f"connection '{args.name}' {outcome}")


def cmd_verify(args) -> None:
    cfg = load_config()
    name = resolve_connection(cfg, args.name)
    conn, cluster, cred = _resolve(cfg, name)
    _check_inspector(cfg, args.inspect_with)
    inspector = args.inspect_with or conn.get("inspect_with")
    print(f"verifying connection '{name}' ...")
    result = _live_check(cfg, conn["cluster"], cluster, cred, inspector)
    _print_check(result)
    previous = conn.get("verified") or {}
    drift = []
    if (
        previous.get("caps") is not None
        and result["caps"] is not None
        and previous["caps"] != result["caps"]
    ):
        drift.append(
            f"caps changed since {previous.get('at')}: {previous['caps']} -> {result['caps']}"
        )
    for field in ("keyring", "entity"):
        if previous.get(field) and previous[field] != result[field]:
            drift.append(f"{field} changed: {previous[field]} -> {result[field]}")
    for d in drift:
        _warn(d)

    # One locked write, saved only onto the connection, cluster and credentials
    # that were checked: a connection repointed meanwhile must not get this result.
    creds = [conn["credential"]]
    if inspector and inspector in cfg.merged["credentials"]:
        creds.append(inspector)
    save = _changes_cluster(cluster, result)
    cluster_file = cfg.origin["clusters"][conn["cluster"]]
    paths = [cfg.origin["connections"][name], *([cluster_file] if save else [])]
    check = [cfg.origin["credentials"][c] for c in creds]
    check += [] if save else [cluster_file]

    def mutate(docs):
        fields = ("cluster", "credential", "inspect_with", "expect_tier")
        entry = _stored(docs, cfg, "connections", name, conn, fields)
        stored = _stored(docs, cfg, "clusters", conn["cluster"], cluster, ("conf",))
        for c in creds:
            seen = cfg.merged["credentials"][c]
            _stored(docs, cfg, "credentials", c, seen, ("keyring", "entity"))
        _save_cluster_facts(stored, result, save)
        entry["verified"] = _verified_block(result)
        if args.inspect_with:
            entry["inspect_with"] = args.inspect_with

    _transact_or_fail(paths, mutate, check)
    if not cluster.get("fsid"):
        print(f"pinned cluster '{conn['cluster']}' to fsid {result['fsid']}")
    expect = conn.get("expect_tier")
    if expect and result["tier"] != expect:
        _fail(
            f"connection '{name}' expects tier '{expect}' but live caps classify as '{result['tier']}'",
            4,
        )
    print("ok" if not drift else "ok (with drift, see warnings above)")


def _set_current(cfg: Config, name: str) -> None:
    _transact_or_fail(
        cfg.target_for(CURRENT), lambda doc: doc.__setitem__(CURRENT, name)
    )


def _env_override_note(cfg: Config, name: str) -> None:
    env = os.environ.get("OTTO_CONNECT")
    if env and _lookup(cfg, env)[0] != name:
        label = _label(cfg, name)
        _warn(
            f"OTTO_CONNECT={env} is set and wins in this shell; unset it to use '{label}'"
        )


def cmd_use_connection(args) -> None:
    cfg = load_config()
    name = resolve_connection(cfg, args.name)
    # switch only to the cluster it really is: the same live check as every command
    check_fsid(cfg, name, "otto use", args.allow_fsid_mismatch, "switch")
    _set_current(cfg, name)
    _env_override_note(cfg, name)
    label = _label(cfg, name)
    cluster = cfg.merged["connections"][name]["cluster"]
    own = (cfg.merged["clusters"].get(cluster) or {}).get("name")
    shown = f" (the cluster's own name is '{own}')" if own and own != cluster else ""
    print(f"switched to '{label}'{shown}")


def cmd_current_connection(args) -> None:
    cfg = load_config()
    if not cfg.current:
        _fail("current-connection is not set")
    known = cfg.current in cfg.merged["connections"]
    print(_label(cfg, cfg.current) if known else cfg.current)
    if known:
        _env_override_note(cfg, cfg.current)


def _table(rows: list[list[str]]) -> None:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())


def _dump(data, output: str) -> None:
    if output == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(yaml.safe_dump(data, sort_keys=True, default_flow_style=False), end="")


def _emit(args, items: list[dict], headers: str, cells, empty: str, key="name"):
    """Print items as a table (default), JSON, YAML, or one name per line."""
    if args.output == "name":
        for item in items:
            print(item[key])
    elif args.output in ("json", "yaml"):
        _dump(items, args.output)
    elif not items:
        print(empty)
    else:
        _table([headers.split(), *(cells(i) for i in items)])


def _shown(key: str, entry: dict) -> tuple[str | None, str | None]:
    """(NAME, ALIAS): the cluster's own name, and this machine's nickname for it
    when that differs."""
    own = entry.get("name")
    return own, (key if key != own else None)


def _login_cell(item: dict) -> str:
    """The login, plus what to type when NAME/LOGIN alone cannot pick it (two
    connections made with set-connection for the same Ceph user)."""
    plain = (item["cluster"], f"{item['cluster']}/{item['login']}")
    return (
        item["login"]
        if item["target"] in plain
        else f"{item['login']} ({item['target']})"
    )


def cmd_cluster_ls(args) -> None:
    cfg = load_config()
    items = []
    for n, c in cfg.merged["connections"].items():
        own, alias = _shown(
            c["cluster"], cfg.merged["clusters"].get(c["cluster"]) or {}
        )
        v = c.get("verified") or {}
        cred = cfg.merged["credentials"].get(c["credential"]) or {}
        items.append(
            {
                "target": _label(cfg, n),
                "connection": n,
                "current": n == cfg.current,
                "cluster": c["cluster"],
                "name": own,
                "alias": alias,
                "login": _login(cfg, c),
                "credential": c["credential"],
                "tier": v.get("tier"),
                "tags": c.get("tags") or [],
                "verified": "outdated"
                if _outdated(c, cred)
                else ("yes" if v else "never"),
                "verified_at": v.get("at"),
            }
        )
    items.sort(key=lambda i: (i["cluster"], i["target"] != i["cluster"], i["login"]))
    _emit(
        args,
        items,
        "CURRENT NAME ALIAS LOGIN TIER VERIFIED",
        lambda i: [
            "*" if i["current"] else "",
            i["name"] or "-",
            i["alias"] or "-",
            _login_cell(i),
            i["tier"] or "-",
            _ago(i["verified_at"]) if i["verified"] == "yes" else i["verified"],
        ],
        "no connections defined",
        key="target",
    )


def cmd_get_clusters(args) -> None:
    cfg = load_config()
    items = []
    for key, c in sorted(cfg.merged["clusters"].items()):
        own, alias = _shown(key, c)
        items.append(
            {
                "key": key,
                "name": own,
                "alias": alias,
                "fsid": c.get("fsid"),
                "conf": c["conf"],
            }
        )
    _emit(
        args,
        items,
        "NAME ALIAS FSID CONF",
        lambda i: [
            i["name"] or "-",
            i["alias"] or "-",
            i["fsid"] or "(not pinned)",
            i["conf"],
        ],
        "no clusters defined",
        key="key",
    )


def cmd_get_credentials(args) -> None:
    cfg = load_config()
    items = [
        {"name": name, "entity": c["entity"], "keyring": c["keyring"]}
        for name, c in sorted(cfg.merged["credentials"].items())
    ]
    _emit(
        args,
        items,
        "NAME ENTITY KEYRING",
        lambda i: [i["name"], i["entity"], i["keyring"]],
        "no credentials defined",
    )


def _completion_targets(cfg: Config) -> list[str]:
    """Everything -C accepts without an error."""
    clusters = cfg.merged["clusters"]
    names = {_label(cfg, n) for n in cfg.merged["connections"]} | set(clusters)
    names |= {e["name"] for e in clusters.values() if e.get("name")}
    return sorted(n for n in names if _lookup(cfg, n)[0])


def _completion_clusters(cfg: Config) -> list[str]:
    """Every alias and own name that names exactly one cluster."""
    clusters = cfg.merged["clusters"]
    names = set(clusters) | {e["name"] for e in clusters.values() if e.get("name")}
    return sorted(n for n in names if _find_cluster(cfg, n)[0])


_COMPLETION_LISTS = {
    "targets": _completion_targets,
    "clusters": _completion_clusters,
    "connections": lambda cfg: sorted(cfg.merged["connections"]),
}


# Filled by add_command_config so the completion script lists the real commands.
_COMMAND_PARSERS: dict = {}

_BASH_COMPLETION = r"""# bash completion for otto. Load it with:  source <(otto config completion bash)
# Plain prefix match: compgen -W would expand $(...) in the words it is given.
__otto_reply() {
    local w words
    IFS=$' \t\n' read -rd '' -a words <<< "$1"
    COMPREPLY=()
    for w in "${words[@]}"; do [[ $w == "$cur"* ]] && COMPREPLY+=("$w"); done
}

_otto() {
    local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD-1]}
    local i word cmd="" sub="" npos=0
    for ((i = 1; i < COMP_CWORD; i++)); do
        word=${COMP_WORDS[i]}
        case $word in
            -C|--connect|-o|--output|--cluster|--credential|--user|--inspect-with|--conf|--keyring|--entity|--name|--tag|--expect-tier)
                ((i++)); continue ;;
            -*) continue ;;
        esac
        if [[ -z $cmd ]]; then
            cmd=$word
        elif [[ ($cmd == config || $cmd == cluster) && -z $sub ]]; then
            sub=$word
        else
            ((npos++))
        fi
    done

    case $prev in
        -C|--connect) __otto_reply "$(otto config completion targets 2>/dev/null)"; return ;;
    esac
    if [[ -z $cmd ]]; then
        __otto_reply "@TOP@ -C --connect --allow-fsid-mismatch --help"; return
    fi
    if [[ $cmd == use ]]; then
        ((npos == 0)) && __otto_reply "$(otto config completion targets 2>/dev/null)"
        return
    fi
    if [[ $cmd == rename ]]; then
        ((npos == 0)) && __otto_reply "$(otto config completion clusters 2>/dev/null)"
        return
    fi
    if [[ $cmd == cluster ]]; then
        if [[ -z $sub ]]; then
            __otto_reply "ls"
        elif [[ $prev == -o || $prev == --output ]]; then
            __otto_reply "@OUTPUTS@"
        fi
        return
    fi
    if [[ $cmd != config ]]; then
        COMPREPLY=($(compgen -f -- "$cur")); return
    fi
    if [[ -z $sub ]]; then
        __otto_reply "@CONFIG@"; return
    fi
    case $prev in
        --cluster) __otto_reply "$(otto config get-clusters -o name 2>/dev/null)"; return ;;
        --credential|--user|--inspect-with)
            __otto_reply "$(otto config get-credentials -o name 2>/dev/null)"; return ;;
        -o|--output) __otto_reply "@OUTPUTS@"; return ;;
        --expect-tier) __otto_reply "@TIERS@"; return ;;
        --conf|--keyring) COMPREPLY=($(compgen -f -- "$cur")); return ;;
    esac
    [[ $cur == -* || $npos -gt 0 ]] && return
    case $sub in
        use-connection|verify)
            __otto_reply "$(otto config completion targets 2>/dev/null)" ;;
        delete-connection)
            __otto_reply "$(otto cluster ls -o name 2>/dev/null)" ;;
        set-connection|rename-connection)
            __otto_reply "$(otto config completion connections 2>/dev/null)" ;;
        set-cluster)
            __otto_reply "$(otto config get-clusters -o name 2>/dev/null)" ;;
        delete-cluster)
            __otto_reply "$(otto config completion clusters 2>/dev/null)" ;;
        set-credentials|delete-credential)
            __otto_reply "$(otto config get-credentials -o name 2>/dev/null)" ;;
        completion) __otto_reply "@COMPLETION@" ;;
    esac
}
complete -F _otto otto
"""


def cmd_completion(args) -> None:
    if args.what in _COMPLETION_LISTS:
        # Runs on every <TAB>: stay silent rather than print errors into the shell.
        try:
            names = _COMPLETION_LISTS[args.what](Config())
        except OttoConfigError:
            return
        if names:
            print("\n".join(names))
        return
    script = _BASH_COMPLETION
    for token, words in (
        ("@TOP@", _COMMAND_PARSERS["top"].choices),
        ("@CONFIG@", _COMMAND_PARSERS["config"].choices),
        ("@OUTPUTS@", OUTPUTS),
        ("@TIERS@", TIERS),
        ("@COMPLETION@", ["bash", *_COMPLETION_LISTS]),
    ):
        script = script.replace(token, " ".join(sorted(words)))
    print(script, end="")


def cmd_view(args) -> None:
    cfg = load_config()
    body = {"apiVersion": API_VERSION, "kind": KIND}
    body.update({s: cfg.merged[s] for s in SECTIONS})
    body[CURRENT] = cfg.current
    _dump(body, args.output)


def _freed_name_note(freed: str) -> None:
    """A freed connection name may now select another login or cluster."""
    cfg = load_config()
    name = _lookup(cfg, freed)[0]
    if name:
        conn = cfg.merged["connections"][name]
        _warn(f"`-C {freed}` will now select {conn['cluster']}/{_login(cfg, conn)}")


def _title(cfg: Config, key: str) -> str:
    own, alias = _shown(key, cfg.merged["clusters"].get(key) or {})
    return f'"{own}" (alias {alias})' if own and alias else f'"{own or key}"'


_CRED_FIELDS = ("credential", "inspect_with")  # where a connection names a credential


_USED_BY = {"connections": (), "credentials": _CRED_FIELDS, "clusters": ("cluster",)}


def _every_doc(cfg: Config, docs: dict | None = None):
    """(file, document) for every config file. With DOCS (files locked in a
    transaction), those are used as they are now; the other files are read
    again. Without, as loaded. A missing file is an empty document."""
    for p in cfg.paths:
        if docs is None:
            doc = cfg.docs[p]
        else:
            doc = docs[p] if p in docs else _read_file(p)
        yield p, doc or _empty_doc()


def _every_connection(cfg: Config, docs: dict | None = None):
    """(file, name, connection) for every connection in every config file, even
    one hidden by a same-named connection in an earlier file (see _every_doc)."""
    for p, doc in _every_doc(cfg, docs):
        for name, conn in doc["connections"].items():
            yield p, name, conn


def _plan(cfg: Config, conns: list[str], cluster: str | None = None) -> dict:
    """Deleting these connections also deletes the credentials only they use,
    and every cluster left without a login (a cluster with no login is not
    listed by `otto cluster ls`, so it would only be left behind, unseen)."""
    every = cfg.merged["connections"]
    gone = {(cfg.origin["connections"][n], n) for n in conns}
    rest = [c for p, n, c in _every_connection(cfg) if (p, n) not in gone]
    creds = {every[n]["credential"] for n in conns}
    creds -= {c.get(f) for c in rest for f in _CRED_FIELDS}
    clusters = {every[n]["cluster"] for n in conns} | ({cluster} if cluster else set())
    clusters -= {c["cluster"] for c in rest}
    return {
        "connections": sorted(conns),
        "credentials": sorted(creds & set(cfg.merged["credentials"])),
        "clusters": sorted(clusters & set(cfg.merged["clusters"])),
    }


def _remove(cfg: Config, plan: dict) -> None:
    """Delete everything in PLAN, each from the file that defines it, in one locked
    write: either all of it is deleted or none of it.

    A credential or cluster that any other connection still uses, in any config
    file, stops the delete. Deleting the current connection also clears that
    choice in every file that names it, so a same-named connection in a later
    file is never picked up silently: the person chooses again with `otto use`."""
    items = [
        (cfg.origin[section][name], section, name)
        for section in ("connections", "credentials", "clusters")
        for name in plan.get(section, ())
    ]
    clear = cfg.current is not None and cfg.current in plan.get("connections", ())
    current_files = (
        [p for p, doc in _every_doc(cfg) if doc.get(CURRENT) == cfg.current]
        if clear
        else []
    )
    paths = {p for p, _, _ in items} | set(current_files)

    def mutate(docs):
        gone = {(p, n) for p, s, n in items if s == "connections"}
        staying = [c for p, n, c in _every_connection(cfg, docs) if (p, n) not in gone]
        for p, section, name in items:
            if name not in docs[p][section]:
                raise OttoConfigError(
                    f"'{name}' was changed meanwhile; nothing was deleted, re-run"
                )
            if any(c.get(f) == name for c in staying for f in _USED_BY[section]):
                raise OttoConfigError(
                    f"'{name}' is used by another connection; nothing was deleted"
                )
        for p, section, name in items:
            del docs[p][section][name]
        for p in current_files:
            if docs[p].get(CURRENT) == cfg.current:
                docs[p][CURRENT] = None

    _transact_or_fail(sorted(paths), mutate)


def _after_delete(cfg: Config, plan: dict) -> None:
    if cfg.current in plan["connections"]:
        now = load_config()  # say what is selected now, as the next command sees it
        if now.current is None:
            _warn(
                "that was the current cluster, so none is selected now; "
                "pick one with: otto use NAME"
            )
        else:
            known = now.current in now.merged["connections"]
            label = _label(now, now.current) if known else now.current
            _warn(
                f"that was the current cluster; now '{label}' is current "
                f"(set in {now.current_origin}); change it with: otto use NAME"
            )
    for freed in plan["connections"] + plan["clusters"]:
        _freed_name_note(freed)


def cmd_delete_connection(args) -> None:
    cfg = load_config()
    name, why = _lookup(cfg, args.name)
    if name is None:
        _fail(why)
    conn = cfg.merged["connections"][name]
    login, title = _login(cfg, conn), _title(cfg, conn["cluster"])
    plan = _plan(cfg, [name])
    _remove(cfg, plan)
    if plan["clusters"]:
        _Prompter(False).ok(f"Deleted {title}: {login} was its only login")
    else:
        _Prompter(False).ok(f'Deleted login "{login}" of {title}')
    _after_delete(cfg, plan)


def cmd_delete_cluster(args) -> None:
    cfg = load_config()
    key, why = _find_cluster(cfg, args.name, see="otto config get-clusters")
    if key is None:
        _fail(why)
    conns = _referencing(cfg, "cluster", key)
    # a connection hidden by a same-named one in an earlier file can use it too:
    # then the cluster cannot go, so say so instead of reporting a delete
    gone = {(cfg.origin["connections"][n], n) for n in conns}
    others = sorted(
        f"'{n}' in {p}"
        for p, n, c in _every_connection(cfg)
        if c.get("cluster") == key and (p, n) not in gone
    )
    if others:
        _fail(
            f"cluster '{key}' is also used by connection {', '.join(others)}; "
            "delete or change that first. Nothing was deleted."
        )
    logins = sorted(_login(cfg, cfg.merged["connections"][n]) for n in conns)
    what = _title(cfg, key)
    if conns:
        many = "s" if len(conns) > 1 else ""
        what += f" and its {len(conns)} login{many} ({', '.join(logins)})"
    ui = _Prompter(not args.yes and _on_terminal())
    if conns and not args.yes:
        if not ui.interactive:
            _fail(f"this would delete {what}; to do it, add --yes")
        with _cancellable():
            if not ui.confirm(f"Delete {what}?", default=False):
                raise _Cancelled
    plan = _plan(cfg, conns, key)
    _remove(cfg, plan)
    ui.ok(f"Deleted {what}")
    _after_delete(cfg, plan)


def cmd_delete_credential(args) -> None:
    cfg = load_config()
    if args.name not in cfg.merged["credentials"]:
        _fail(f"no such credential '{args.name}'")
    users = sorted({u for f in _CRED_FIELDS for u in _referencing(cfg, f, args.name)})
    if users:
        _fail(
            f"credential '{args.name}' is used by connection(s): {', '.join(users)}; delete those first"
        )
    _remove(cfg, {"connections": [], "credentials": [args.name], "clusters": []})
    print(f"deleted credential '{args.name}'")


def cmd_rename_connection(args) -> None:
    _check_name("connection", args.new)
    cfg = load_config()
    if args.old not in cfg.merged["connections"]:
        _fail(f"no such connection '{args.old}'")
    if args.new in cfg.merged["connections"]:
        _fail(f"connection '{args.new}' already exists")

    path = cfg.origin["connections"][args.old]
    selected = cfg.current == args.old
    paths = [path] + ([cfg.current_origin] if selected else [])

    def mutate(docs):
        conns = docs[path]["connections"]
        if args.old not in conns:
            raise OttoConfigError(f"connection '{args.old}' was changed concurrently")
        if args.new in conns:
            raise OttoConfigError(f"connection '{args.new}' was created concurrently")
        conns[args.new] = conns.pop(args.old)
        if selected and docs[cfg.current_origin].get(CURRENT) == args.old:
            docs[cfg.current_origin][CURRENT] = args.new  # stays selected

    _transact_or_fail(paths, mutate)
    print(f"renamed connection '{args.old}' to '{args.new}'")
    _freed_name_note(args.old)


# ---- otto config add: one step, and asks when a person is at the terminal ----


def _keyring_problem(path: str, entity: str) -> str | None:
    if not path:
        return "enter the path of a keyring file"
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path) or not os.access(path, os.R_OK):
        return f"{path} is not a readable file"
    if any(c.isspace() for c in path):
        return f"{path} contains whitespace, which Ceph cannot pass safely"
    if not _keyring_entities(path).get(entity):
        return f"{path} has no key for {entity}"
    return None


def _find_keyring(conf: str, entity: str) -> str | None:
    """Find the keyring the way the ceph CLI does: the conf's `keyring` setting,
    else Ceph's defaults, which use the cluster name taken from the conf's file
    name (backup.conf -> /etc/ceph/backup.client.admin.keyring)."""
    setting = _conf_lookup(conf, entity, "keyring", "--show-config-value")
    candidates = [p.strip() for p in (setting or "").split(",") if p.strip()]
    if not setting:  # ceph-conf missing or failed: Ceph's default keyring setting
        name = os.path.basename(conf)
        cluster = name.removesuffix(".conf") if name.endswith(".conf") else "ceph"
        candidates = [
            f"/etc/ceph/{cluster}.{entity}.keyring",
            f"/etc/ceph/{cluster}.keyring",
            "/etc/ceph/keyring",
            "/etc/ceph/keyring.bin",
        ]
    for path in candidates:
        path = os.path.abspath(os.path.expanduser(path))
        if not _keyring_problem(path, entity):
            return path
    return None


_LISTED_BY = {
    "clusters": "otto config get-clusters",
    "credentials": "otto config get-credentials",
    "connections": "otto config view",
}


def _name_problem(cfg: Config, name: str, fsid: str, mine=()) -> str | None:
    """Why NAME cannot be used for the cluster with this fsid, or None.
    `mine` holds that cluster's own entries, which may keep their names."""
    if not CLUSTER_NAME_RE.fullmatch(name):
        return (
            f"'{name}' is not a valid name: use lowercase letters, digits, '.', '_' or "
            "'-', start with a letter or digit, at most 63 characters"
        )
    for section in SECTIONS:
        if name in cfg.merged[section] and name not in mine:
            return f"'{name}' is already used here (see: {_LISTED_BY[section]})"
    for key, entry in cfg.merged["clusters"].items():
        if entry.get("name") == name and entry.get("fsid") != fsid:
            return f"'{name}' is already the name of another cluster ('{key}')"
    return None


def _decide_name(ui: _Prompter, cfg: Config, own, why: str, fsid: str, mine=()):
    """Return (what this machine calls it, the cluster's own name afterwards,
    write) where write is None, "store" (name an unnamed cluster) or "rename".
    `mine`: names left by an earlier entry for this cluster, free to reuse."""

    def check(name):
        return _name_problem(cfg, name, fsid, mine)

    ui.say()
    if own:
        ui.say(f"This cluster already has a name: {ui.bold(own)}")
        ui.say(ui.dim("It is stored in the cluster, so everyone who connects sees it."))
        if not ui.interactive:
            if check(own):
                _fail(
                    check(own)
                    + "; run `otto config add` on a terminal to pick an alias"
                )
            return own, own, None
        options = [
            (f'Keep "{own}"', "recommended"),
            ("Give it an alias on this machine only", f'the cluster stays "{own}"'),
            ("Rename the cluster", "everyone who connects will see the new name"),
        ]
        while True:
            choice = ui.choose("Which name do you want to use?", options, 1)
            if choice == 1:
                if check(own):
                    ui.warn(check(own))
                    continue
                return own, own, None
            new = ui.ask(
                "Alias on this machine" if choice == 2 else "New name",
                check=lambda n: check(n) or (n == own and "that is its current name"),
            )
            if choice == 2:
                return new, own, None
            if ui.confirm(
                f'Rename the cluster from "{own}" to "{new}" for everyone?',
                default=False,
            ):
                return new, new, "rename"

    readable = why == NOT_SET
    if readable:
        ui.say("This cluster has no name yet.")
    else:
        ui.warn(f"Could not read the cluster's own name: {why}")
    if not ui.interactive:
        _fail(
            "this cluster has no name otto can use; run `otto config add` on a terminal to choose one"
        )
    name = ui.ask("Name for this cluster", check=check)
    store = readable and ui.confirm(
        f'Also store "{name}" in the cluster, so everyone who connects sees it?',
        default=False,
    )
    return name, (name if store else None), ("store" if store else None)


def cmd_add(args) -> None:
    with _cancellable():
        _add(args, _Prompter(not args.yes and _on_terminal()))


def _add(args, ui: _Prompter) -> None:
    _check_entity(args.entity)
    conf = _check_path("conf", args.conf)
    cfg = load_config()

    if args.keyring:
        keyring = os.path.abspath(os.path.expanduser(args.keyring))
        problem = _keyring_problem(keyring, args.entity)
        if problem:
            _fail(problem)
    else:
        keyring = _find_keyring(conf, args.entity)
        if keyring:
            ui.ok(f"Found the keyring for {args.entity}: {keyring}")
        elif ui.interactive:
            reply = ui.ask(
                f"Keyring file for {args.entity}",
                check=lambda p: _keyring_problem(p, args.entity),
            )
            keyring = os.path.abspath(os.path.expanduser(reply))
        else:
            _fail(
                f"no keyring with a key for {args.entity} found via {conf} or /etc/ceph; "
                "pass --keyring"
            )

    ui.say(f"Connecting as {args.entity} ...")
    result = _live_check(
        cfg,
        None,
        {"conf": conf, "fsid": None},
        {"keyring": keyring, "entity": args.entity},
        None,
    )
    fsid = result["fsid"]
    ui.ok(f"Reached cluster {fsid}")
    ui.ok(f"Logged in as {args.entity} (permissions: {result['tier']})")
    stale = None
    for key, entry in cfg.merged["clusters"].items():
        if entry.get("fsid") == fsid:
            if _referencing(cfg, "cluster", key):
                _add_to_existing(args, ui, cfg, key, result, keyring)
                return
            stale = key  # here, but without a login (e.g. from set-cluster): replace it

    own = result["name"]
    mine = {stale} if stale else ()
    local, kv, write = _decide_name(ui, cfg, own, result["name_why"], fsid, mine)
    if write == "rename":
        own_line = f"{own} -> {local}  (will be renamed)"
    elif write == "store":
        own_line = f"{local}  (will be stored in the cluster)"
    else:
        own_line = kv or "none"
    ui.say()
    ui.say(ui.bold("Summary"))
    for label, value in (
        ("Name", own_line),
        ("Alias", f"{local}  (this machine only)" if local != kv else "-"),
        ("Cluster", f"{fsid}  (pinned)"),
        ("Config", conf),
        ("Login", f"{args.entity}  {ui.dim(keyring)}"),
        ("Permissions", result["tier"]),
    ):
        ui.say(f"  {label:<14}{value}")
    ui.say()
    if ui.interactive and not ui.confirm("Add it?", default=True):
        raise _Cancelled
    switch = args.use or (
        ui.interactive and ui.confirm(f'Switch to "{local}" now?', default=True)
    )

    if write:
        write_name(
            result["snap"], keyring, args.entity, local, overwrite=write == "rename"
        )
        ui.ok(
            f'Renamed the cluster to "{local}"'
            if write == "rename"
            else f'Stored "{local}" in the cluster'
        )
    path = (
        cfg.origin["clusters"][stale] if stale else cfg.target_for("connections", local)
    )

    def mutate(docs):
        doc = docs[path]
        if stale:  # the entry without a login, and an unused credential of its name
            if (doc["clusters"].get(stale) or {}).get("fsid") != fsid:
                raise OttoConfigError(f"cluster '{stale}' was changed meanwhile")
            users = [
                f"'{n}' in {p}"
                for p, n, c in _every_connection(cfg, docs)
                if c.get("cluster") == stale
            ]
            if users:  # e.g. a connection hidden by a same-named one in another file
                raise OttoConfigError(
                    f"cluster '{stale}' is used by connection {', '.join(users)}"
                )
            del doc["clusters"][stale]
            used = any(
                c.get(f) == stale
                for _, _, c in _every_connection(cfg, docs)
                for f in _CRED_FIELDS
            )
            if not used:
                doc["credentials"].pop(stale, None)
        for section in SECTIONS:
            if local in doc[section]:
                raise OttoConfigError(f"'{local}' was added meanwhile")
        doc["clusters"][local] = {"conf": conf, "fsid": fsid, "name": kv}
        doc["credentials"][local] = {"keyring": keyring, "entity": args.entity}
        doc["connections"][local] = _connection_entry(local, local, result)

    if write:
        _save_after_remote(
            [path],
            mutate,
            f'the cluster now calls itself "{local}" for everyone',
            f"run the same otto config add again and keep the name {local}",
        )
    else:
        _transact_or_fail([path], mutate)
    ui.ok(f'Added "{local}"')
    if switch:
        _set_current(load_config(), local)
        ui.ok(f'Switched to "{local}"   {ui.dim("try: otto ceph -s")}')
    else:
        ui.say(ui.dim(f"Switch to it with: otto use {local}"))


def _logins_of(cfg: Config, key: str) -> tuple[list[str], set[str]]:
    """A cluster's connections, and the credentials they log in with."""
    conns = _referencing(cfg, "cluster", key)
    return conns, {cfg.merged["connections"][n]["credential"] for n in conns}


def _entries_of(cfg: Config, key: str) -> set[str]:
    """The cluster entry, its connections and their credentials."""
    conns, creds = _logins_of(cfg, key)
    return {key, *conns, *creds}


def _add_to_existing(args, ui: _Prompter, cfg: Config, key: str, result, keyring):
    """The cluster is already here: add another login, rename the cluster, or
    change what this machine calls it."""
    if _name_known(result):
        own = result["name"]
    else:
        own = cfg.merged["clusters"][key].get("name")
    login = args.entity.removeprefix("client.")
    conns, _ = _logins_of(cfg, key)
    logins = {_login(cfg, cfg.merged["connections"][n]) for n in conns}
    known = f' (the cluster calls itself "{own}")' if own and own != key else ""
    ui.say()
    ui.say(f"This cluster is already added here as {ui.bold(key)}{known}.")
    actions = (
        []
        if login in logins
        else [("login", f"Add {args.entity} as another login", "recommended")]
    )
    actions += [
        ("rename", "Rename the cluster", "everyone who connects will see the new name"),
        ("alias", "Change the alias on this machine", "only here"),
    ]
    if ui.interactive:
        names = [a[0] for a in actions]
        # Enter picks the harmless choice: a new login, else a local alias
        default = names.index("login" if "login" in names else "alias") + 1
        choice = ui.choose("What do you want to do?", [a[1:] for a in actions], default)
        action = names[choice - 1]
    elif login not in logins:
        action = "login"
    else:
        _fail(
            f"this cluster is already added here as '{key}' with login {login}; "
            f"to rename it: otto rename {key}"
        )
    if action == "login":
        _add_login(args, ui, cfg, key, result, keyring)
    elif action == "rename":
        _rename_existing(ui, cfg, key, own, result, keyring, args.entity)
    else:
        _change_alias_here(ui, cfg, key, own, result["fsid"])


def _inspect(cfg: Config, key: str, result: dict) -> str | None:
    """Read a login's permissions through an admin login of the same cluster
    (a read-only login may not read its own). Returns that credential."""
    for c in sorted(cfg.merged["connections"].values(), key=lambda c: c["credential"]):
        cred = cfg.merged["credentials"].get(c["credential"])
        if (
            c["cluster"] != key
            or not cred
            or (c.get("verified") or {}).get("tier") != "admin"
        ):
            continue
        caps, _ = probe_caps(
            result["snap"], cred["keyring"], cred["entity"], result["entity"]
        )
        if caps is not None:
            result["caps"], result["inspected_by"] = caps, cred["entity"]
            result["tier"], result["reasons"] = classify_caps(caps)
            return c["credential"]
    return None


def _add_login(args, ui: _Prompter, cfg: Config, key, result, keyring) -> None:
    login = args.entity.removeprefix("client.")
    name = f"{key}-{login}"  # an internal name; people type KEY/LOGIN
    if not NAME_RE.fullmatch(name):
        _fail(
            f"this login would be saved as '{name}', longer than the 63 characters "
            "a name may have; first give the cluster a shorter alias on this machine: "
            f"otto config add --conf {args.conf}, then 'Change the alias'"
        )
    for section in ("credentials", "connections"):
        if name in cfg.merged[section]:
            _fail(f"'{name}' is already used here (see: {_LISTED_BY[section]})")
    inspector = _inspect(cfg, key, result) if result["caps"] is None else None
    if inspector:
        ui.ok(
            f"Permissions of {args.entity}: {result['tier']} (read by {result['inspected_by']})"
        )
    switch = args.use or (
        ui.interactive and ui.confirm(f'Switch to "{key}/{login}" now?', default=False)
    )
    path = cfg.origin["clusters"][key]

    def mutate(doc):
        # still the cluster that was checked, and the names still free
        if (
            (doc["clusters"].get(key) or {}).get("fsid") != result["fsid"]
            or name in doc["credentials"]
            or name in doc["connections"]
        ):
            raise OttoConfigError(f"'{key}' was changed meanwhile; nothing written")
        doc["credentials"][name] = {"keyring": keyring, "entity": args.entity}
        doc["connections"][name] = _connection_entry(
            key, name, result, inspect_with=inspector
        )

    _transact_or_fail(path, mutate)
    label = _label(load_config(), name)
    ui.ok(
        f'Added login "{login}" to "{key}"   {ui.dim(f"use it with: otto -C {label} ...")}'
    )
    if switch:
        _set_current(load_config(), name)
        ui.ok(f'Switched to "{label}"')


def _rekey_problem(cfg: Config, key: str, new: str) -> str | None:
    """Why this machine's entries for cluster KEY cannot be renamed to NEW."""
    try:
        _plan_rekey(cfg, key, new)
    except OttoConfigError as e:
        return str(e)
    return None


def _rekey_layout_or_fail(cfg: Config, key: str) -> None:
    """Stop before asking for a new name that no name could satisfy."""
    problem = _rekey_layout_problem(cfg, key)
    if problem:
        _fail(f"{problem}. Nothing was changed.")


def _ask_new_alias(ui: _Prompter, cfg: Config, key: str, fsid: str, prompt: str) -> str:
    _rekey_layout_or_fail(cfg, key)
    mine = _entries_of(cfg, key)

    def check(n):
        if n == key:
            return "that is what it is called here now"
        return _name_problem(cfg, n, fsid, mine) or _rekey_problem(cfg, key, n)

    return ui.ask(prompt, check=check)


def _ask_new_name(ui: _Prompter, cfg: Config, key, own, fsid, question) -> str:
    """Ask for the cluster's new own name, then ask to confirm (default No)."""
    if key == own:  # no alias: this machine's entries follow the new name
        _rekey_layout_or_fail(cfg, key)
    mine = _entries_of(cfg, key)

    def check(n):
        if n == own:
            return "that is its name now"
        problem = _name_problem(cfg, n, fsid, mine)
        if not problem and key == own:  # no alias: this machine follows the name
            problem = _rekey_problem(cfg, key, n)
        return problem

    new = ui.ask("New name", check=check)
    if not ui.confirm(question(new), default=False):
        raise _Cancelled
    return new


def _save_after_remote(paths, mutate, done: str, finish: str) -> None:
    """Save local changes after the cluster itself was changed. Everything that
    can be checked was checked before that; if saving still fails, say what did
    change and how to finish, so the two never disagree silently."""
    try:
        transact_files(paths, mutate)
    except (OttoConfigError, OSError) as e:
        why = (e.strerror or str(e)) if isinstance(e, OSError) else str(e)
        _fail(f"{done}, but otto could not save that here: {why}\nto finish: {finish}")


def _store_new_name(cfg: Config, key, own, new, fsid, snap, keyring, entity) -> None:
    """Rename the cluster itself, then this machine's entries for it."""
    # without an alias this machine follows the new name: plan that first, so a
    # clash or a too-long name stops the rename before the cluster changes
    plan = None
    if key == own:
        try:
            plan = _plan_rekey(cfg, key, new)
        except OttoConfigError as e:
            _fail(f"{e}; nothing was changed")
    write_name(snap, keyring, entity, new, overwrite=True)
    origin = cfg.origin["clusters"][key]

    def mutate(docs):
        entry = docs[origin]["clusters"].get(key)
        if entry is None or entry.get("fsid") != fsid:
            raise OttoConfigError(f"cluster '{key}' was changed meanwhile")
        entry["name"] = new
        if plan:
            _apply_rekey(cfg, plan, docs)

    _save_after_remote(
        [origin, *(_rekey_paths(cfg, plan) if plan else [])],
        mutate,
        f'the cluster is now called "{new}" for everyone',
        f"otto config verify {key}  (it reads the new name); "
        f"then otto rename {key} to rename it here too",
    )


def _rename_existing(ui: _Prompter, cfg: Config, key, own, result, keyring, entity):
    old = f'"{own}"' if own else "(no name)"
    new = _ask_new_name(
        ui,
        cfg,
        key,
        own,
        result["fsid"],
        lambda n: f'Rename the cluster from {old} to "{n}" for everyone?',
    )
    fsid = result["fsid"]
    _store_new_name(cfg, key, own, new, fsid, result["snap"], keyring, entity)
    ui.ok(f'Renamed the cluster to "{new}"')


def _change_alias_here(ui: _Prompter, cfg: Config, key, own, fsid) -> None:
    new = _ask_new_alias(ui, cfg, key, fsid, "Alias on this machine")
    _rekey(cfg, key, new)
    ui.ok(
        f'No alias any more: it is "{own}" here too'
        if new == own
        else f'Alias on this machine: "{new}"'
    )


def _plan_rekey(cfg: Config, old: str, new: str) -> dict:
    """What renaming this machine's cluster entry OLD to NEW changes: the cluster
    entry, the connections and credentials `add` named after it, and every
    reference to them. All of it is checked here, before anything is written:
    each new name must fit and be free, and everything involved must be in one
    config file (one locked write can then change it all together).
    Raises OttoConfigError with the reason."""
    problem = _rekey_layout_problem(cfg, old)
    if problem:
        raise OttoConfigError(problem)
    path, conns, creds = _rekey_parts(cfg, old)

    def renamed(n: str) -> str:
        return new + n[len(old) :]

    moves = {
        "clusters": {old: new},
        "connections": {n: renamed(n) for n in conns if _named_after(n, old)},
        "credentials": {n: renamed(n) for n in creds if _named_after(n, old)},
    }
    taken = {
        section: {
            n for doc in cfg.docs.values() for n in ((doc or {}).get(section) or {})
        }
        for section in SECTIONS
    }
    for section, moved in moves.items():
        for src, dst in moved.items():
            if not NAME_RE.fullmatch(dst):
                raise OttoConfigError(
                    f"'{src}' would become '{dst}', longer than the 63 characters "
                    "a name may have; choose a shorter name"
                )
            if dst in taken[section] and dst not in moved:
                raise OttoConfigError(
                    f"'{dst}' is already used here (see: {_LISTED_BY[section]})"
                )
    return {"old": old, "new": new, "path": path, "moves": moves}


def _named_after(name: str, key: str) -> bool:
    """Is NAME one that `otto config add` made for cluster KEY (KEY, KEY-LOGIN)?"""
    return name == key or name.startswith(f"{key}-")


def _rekey_parts(cfg: Config, key: str):
    """(file of cluster KEY, its connections, the credentials they use)."""
    conns, creds = _logins_of(cfg, key)
    return (
        cfg.origin["clusters"][key],
        conns,
        {n for n in creds if n in cfg.origin["credentials"]},
    )


def _rekey_layout_problem(cfg: Config, key: str) -> str | None:
    """Why cluster KEY's entries cannot be renamed whatever the new name: the
    cluster, its connections, the credentials named after it, and every
    connection that refers to them must be in one file, so one locked write can
    change them all together."""
    path, conns, creds = _rekey_parts(cfg, key)
    moved = {n for n in creds if _named_after(n, key)}
    files = {path, *(cfg.origin["connections"][n] for n in conns)}
    files |= {cfg.origin["credentials"][n] for n in moved}
    files |= {
        p
        for p, _, c in _every_connection(cfg)
        if c.get("cluster") == key or any(c.get(f) in moved for f in _CRED_FIELDS)
    }
    if files != {path}:
        return (
            f"cluster '{key}', its logins and every connection that uses them must "
            f"be in one config file to rename them; move them into {path}"
        )
    return None


def _rekey_paths(cfg: Config, plan: dict) -> list:
    """The files a rename changes: the plan's file, and the current choice's."""
    moved_current = cfg.current in plan["moves"]["connections"]
    return [plan["path"], *([cfg.current_origin] if moved_current else [])]


def _apply_rekey(cfg: Config, plan: dict, docs: dict) -> None:
    """Make the renames of PLAN in DOCS, which are locked in a transaction."""
    doc = docs[plan["path"]]
    creds = plan["moves"]["credentials"]
    # what the plan checked in the other files must still hold (read again now)
    for p, other in _every_doc(cfg, docs):
        if p == plan["path"]:
            continue
        for c in other["connections"].values():
            if c.get("cluster") == plan["old"] or any(
                c.get(f) in creds for f in _CRED_FIELDS
            ):
                raise OttoConfigError(
                    f"a connection in {p} now uses '{plan['old']}'; nothing was renamed"
                )
        for section, moved in plan["moves"].items():
            if any(dst in other[section] for dst in moved.values()):
                raise OttoConfigError(
                    f"a new name for '{plan['old']}' is now used in {p}; "
                    "nothing was renamed"
                )
    for section, moved in plan["moves"].items():
        if any(src not in doc[section] for src in moved):
            raise OttoConfigError(f"cluster '{plan['old']}' was changed meanwhile")
        entries = {dst: doc[section].pop(src) for src, dst in moved.items()}
        if any(dst in doc[section] for dst in entries):
            raise OttoConfigError(f"a name for '{plan['old']}' was taken meanwhile")
        doc[section].update(entries)
    for c in doc["connections"].values():
        if c["cluster"] == plan["old"]:
            c["cluster"] = plan["new"]
        for f in _CRED_FIELDS:
            if c.get(f) in creds:
                c[f] = creds[c[f]]
    current = plan["moves"]["connections"].get(cfg.current)
    if current and docs[cfg.current_origin].get(CURRENT) == cfg.current:
        docs[cfg.current_origin][CURRENT] = current  # stays selected


def _rekey(cfg: Config, old: str, new: str) -> None:
    """Rename this machine's entries for cluster OLD to NEW, or explain why not."""
    try:
        plan = _plan_rekey(cfg, old, new)
    except OttoConfigError as e:
        _fail(f"{e}; nothing was changed")
    _transact_or_fail(
        _rekey_paths(cfg, plan), lambda docs: _apply_rekey(cfg, plan, docs)
    )


def _rename_target(cfg: Config, target: str) -> tuple[str, bool]:
    """(cluster, is_alias): an alias is renamed here only; a cluster's own name
    is renamed in the cluster."""
    key, why = _find_cluster(cfg, target)
    if key is None:
        _fail(why)
    return key, cfg.merged["clusters"][key].get("name") != target


def _writer(cfg: Config, key: str) -> str:
    """The login that writes the cluster's name: an admin one, `add`'s first."""
    conns = _referencing(cfg, "cluster", key)
    if not conns:
        _fail(f"cluster '{key}' has no login yet (see: otto config add)")
    admin = [
        n
        for n in conns
        if (cfg.merged["connections"][n].get("verified") or {}).get("tier") == "admin"
    ]
    return min(admin or conns, key=lambda n: n != key)


def cmd_rename(args) -> None:
    ui = _Prompter(_on_terminal())
    if not ui.interactive:
        _fail("otto rename asks for the new name; run it on a terminal")
    cfg = load_config()
    key, is_alias = _rename_target(cfg, args.name)
    entry = cfg.merged["clusters"][key]
    own = entry.get("name")
    with _cancellable():
        if is_alias:
            known = (
                f'the cluster calls itself "{own}"'
                if own
                else "the cluster has no name of its own"
            )
            ui.say(f"{ui.bold(key)} is the alias on this machine ({known}).")
            new = _ask_new_alias(ui, cfg, key, entry.get("fsid"), "New alias")
            _rekey(cfg, key, new)
            same = " (now the same as the cluster's own name)" if new == own else ""
            ui.ok(f"Renamed the alias: {key} -> {new}{same}")
            return
        ui.say(
            f"{ui.bold(own)} is the cluster's own name: everyone who connects sees it."
        )
        new = _ask_new_name(
            ui,
            cfg,
            key,
            own,
            entry.get("fsid"),
            lambda n: "Rename the cluster for everyone?",
        )
    name = _writer(cfg, key)
    _, cluster, cred, conf, keyring = _pinned(cfg, name)
    snap, live = _reach(
        f"'{own}': ",
        f"cluster '{key}'",
        conf,
        keyring,
        cred["entity"],
        pinned=cluster["fsid"],
    )
    if live != cluster["fsid"]:
        _fail(
            f"the cluster at {conf} is not the one pinned as '{key}'; nothing was changed",
            2,
        )
    now, _ = probe_name(snap, keyring, cred["entity"])
    if now not in (None, own):
        _fail(f"the cluster now calls itself '{now}', not '{own}'; nothing was changed")
    fsid = cluster["fsid"]
    _store_new_name(cfg, key, own, new, fsid, snap, keyring, cred["entity"])
    ui.ok(f"Renamed the cluster: {own} -> {new}")


def _flag(parser, *names_then_help: str) -> None:
    """An on/off option: _flag(p, "-y", "--yes", "help text")."""
    *names, text = names_then_help
    parser.add_argument(*names, action="store_true", help=text)


_TARGET_HELP = (
    "the cluster's name or alias, NAME/LOGIN for another login, or a connection"
)


def _output_flag(parser) -> None:
    parser.add_argument(
        "-o",
        "--output",
        choices=OUTPUTS,
        default="table",
        help="table (default), json, yaml, or name: one per line, for scripts",
    )


def add_command_config(subparsers) -> None:
    p = subparsers.add_parser(
        "config",
        help="Manage multi-cluster connections (kubeconfig-style)",
        description="Clusters (where) + credentials (who) = connections. Config file: "
        f"{DEFAULT_CONFIG}, or the os.pathsep-separated list in OTTO_CONFIG.",
    )
    p.set_defaults(skip_connection=True, func=lambda a: p.print_help())
    sub = p.add_subparsers(dest="config_command", metavar="")

    sc = sub.add_parser(
        "set-cluster", help="Register or update a cluster (ceph.conf path)"
    )
    sc.add_argument("name")
    sc.add_argument("--conf", required=True, help="path to the cluster's ceph.conf")
    _flag(
        sc,
        "--reset-fsid",
        "forget the pinned fsid and the cluster's name; the next verify reads both again",
    )
    sc.set_defaults(func=cmd_set_cluster)

    scr = sub.add_parser(
        "set-credentials", help="Register or update a credential (keyring + entity)"
    )
    scr.add_argument("name")
    scr.add_argument("--keyring", required=True)
    scr.add_argument(
        "--entity",
        "--name",
        dest="entity",
        required=True,
        help="cephx entity, e.g. client.admin",
    )
    scr.set_defaults(func=cmd_set_credentials)

    sn = sub.add_parser("set-connection", help="Define a connection and verify it live")
    sn.add_argument("name")
    sn.add_argument("--cluster", required=True)
    sn.add_argument("--credential", "--user", dest="credential", required=True)
    sn.add_argument(
        "--tag", action="append", default=[], help="label such as prod (repeatable)"
    )
    sn.add_argument(
        "--expect-tier",
        choices=TIERS,
        help="refuse unless the live caps classify as this tier",
    )
    sn.add_argument(
        "--inspect-with",
        metavar="CREDENTIAL",
        help="credential allowed to run 'auth get' (reads the caps)",
    )
    _flag(sn, "--force", "register even if --expect-tier does not match")
    sn.set_defaults(func=cmd_set_connection)

    v = sub.add_parser(
        "verify", help="Re-check a connection live (fsid, authentication, caps drift)"
    )
    v.add_argument("name", help=_TARGET_HELP)
    v.add_argument("--inspect-with", metavar="CREDENTIAL")
    v.set_defaults(func=cmd_verify)

    u = sub.add_parser(
        "use-connection", help="Set the default connection (checks its fsid first)"
    )
    u.add_argument("name", help=_TARGET_HELP)
    u.set_defaults(func=cmd_use_connection)

    sub.add_parser(
        "current-connection", help="Print the default connection"
    ).set_defaults(func=cmd_current_connection)
    for kind, func in (
        ("clusters", cmd_get_clusters),
        ("credentials", cmd_get_credentials),
    ):
        g = sub.add_parser(f"get-{kind}", help=f"List {kind}")
        _output_flag(g)
        g.set_defaults(func=func)

    cp = sub.add_parser(
        "completion",
        help="Print a shell completion script: source <(otto config completion bash)",
    )
    cp.add_argument(
        "what",
        choices=["bash", *_COMPLETION_LISTS],
        help="bash: the completion script; targets: the names -C accepts; "
        "clusters: cluster names and aliases; connections: connection names",
    )
    cp.set_defaults(func=cmd_completion)

    vw = sub.add_parser("view", help="Show the merged configuration")
    vw.add_argument("-o", "--output", choices=["yaml", "json"], default="yaml")
    vw.set_defaults(func=cmd_view)

    dn = sub.add_parser(
        "delete-connection",
        help="Delete one login: NAME/LOGIN",
        description="Delete one login, and its credential if nothing else uses it. "
        "If it was the cluster's last login, the cluster is deleted too.",
    )
    dn.add_argument("name", help=_TARGET_HELP)
    dn.set_defaults(func=cmd_delete_connection)
    dc = sub.add_parser(
        "delete-cluster", help="Delete a cluster and all its logins (asks first)"
    )
    dc.add_argument("name", help="the cluster's name or alias")
    _flag(dc, "-y", "--yes", "do not ask")
    dc.set_defaults(func=cmd_delete_cluster)
    dr = sub.add_parser("delete-credential", help="Delete a credential")
    dr.add_argument("name")
    dr.set_defaults(func=cmd_delete_credential)

    rn = sub.add_parser("rename-connection", help="Rename a connection")
    rn.add_argument("old")
    rn.add_argument("new")
    rn.set_defaults(func=cmd_rename_connection)

    ad = sub.add_parser(
        "add",
        help="Add a cluster in one step (asks when it needs a decision)",
        description="Add a cluster, its login and a connection, all under one name. "
        "On a terminal it asks before every decision; with --yes, or when not on a "
        "terminal, it never asks and never changes the cluster's name. "
        "For a cluster that is already added it adds another login, renames the "
        "cluster, or changes its alias on this machine.",
    )
    ad.add_argument("--conf", required=True, help="the cluster's ceph.conf")
    ad.add_argument(
        "--keyring", help="keyring file (default: found the way the ceph CLI finds it)"
    )
    ad.add_argument(
        "--entity", default="client.admin", help="Ceph user (default: client.admin)"
    )
    _flag(ad, "--use", "switch to it after adding it")
    _flag(
        ad,
        "-y",
        "--yes",
        "never ask: use the flags and safe defaults (automatic when not on a terminal)",
    )
    ad.set_defaults(func=cmd_add)

    us = subparsers.add_parser(
        "use",
        help="Switch cluster after checking its fsid: NAME, ALIAS or NAME/LOGIN",
    )
    us.add_argument("name", help=_TARGET_HELP)
    us.set_defaults(func=cmd_use_connection, skip_connection=True)
    rename = subparsers.add_parser(
        "rename",
        help="Rename a cluster: its alias on this machine, or its own name (asks)",
    )
    rename.add_argument("name", help="the cluster's name or alias")
    rename.set_defaults(func=cmd_rename, skip_connection=True)
    subparsers.add_parser(
        "current",
        help="Show the current cluster (short for: otto config current-connection)",
    ).set_defaults(func=cmd_current_connection, skip_connection=True)
    cl = subparsers.add_parser("cluster", help="List the clusters you can use")
    cl.set_defaults(skip_connection=True, func=lambda a: cl.print_help())
    ls = cl.add_subparsers(dest="cluster_command", metavar="").add_parser(
        "ls",
        help="List clusters and their logins",
        description="List every cluster and login. TIER is from the last live "
        "check (otto config add / set-connection / verify), shown in VERIFIED; "
        "every command re-checks only the fsid, so run otto config verify NAME "
        "after a user's caps change. 'outdated' means the keyring path or user "
        "changed since that check.",
    )
    _output_flag(ls)
    ls.set_defaults(func=cmd_cluster_ls)

    _COMMAND_PARSERS.update(top=subparsers, config=sub)


# ---- raw passthrough: otto [-C NAME] ceph -- ... / otto [-C NAME] exec -- ... ----


def _run_passthrough(argv: list[str]) -> None:
    rc = run_child(argv)
    sys.exit(128 - rc if rc < 0 else rc)


def run_child(argv: list) -> int:
    """Run ARGV in the foreground and return its exit status (negative: the
    signal that ended it).

    A SIGTERM or SIGHUP sent to otto alone (a service manager, `kill PID`) is
    passed on, and otto waits for the child before it exits and removes the conf
    snapshot the child may still be reading. Set up before the child starts, so
    a signal in between is passed on too. Ctrl+C reaches the child from the
    terminal itself; otto keeps waiting for it."""
    proc = None
    early: list[int] = []

    def forward(signum, _frame):
        if proc is None:
            early.append(signum)
        else:
            proc.send_signal(signum)

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, forward)
    try:
        proc = subprocess.Popen(argv)
    except FileNotFoundError:
        _fail(f"{argv[0]}: command not found", 127)
    except OSError as e:
        _fail(f"{argv[0]}: {e.strerror}", 126)
    for signum in early:
        proc.send_signal(signum)
    while True:
        try:
            return proc.wait()
        except KeyboardInterrupt:
            continue


def script_target_lines() -> list[str]:
    """Shell lines that pin a script otto prints to the cluster it checked.

    The script runs later in another shell (`otto -C prod upmap-remapped | sh`),
    which never sees otto's CEPH_ARGS. These lines set the target there and check
    the fsid again when the script runs. They name the original conf: the private
    copy is gone once otto exits. Empty when no cluster was selected."""
    if not _ACTIVE:
        return []
    fsid = _ACTIVE["fsid"]
    # unquoted inside, like activation: Ceph splits CEPH_ARGS on whitespace,
    # and conf and keyring paths never contain any (_check_path)
    ceph_args = (
        f"--conf {_ACTIVE['conf']} --keyring {_ACTIVE['keyring']} "
        f"--name {_ACTIVE['entity']}"
    )
    return [
        f"# made by otto for connection {_ACTIVE['connection']}, cluster fsid {fsid}",
        f"export CEPH_ARGS={shlex.quote(ceph_args)}",
        "unset CEPH_CONF CEPH_KEYRING",
        "live=$(ceph fsid) || exit 1",
        (
            f'if [ "$live" != {fsid} ]; then echo "otto: this script is for cluster '
            f'{fsid}, not $live" >&2; exit 1; fi'
        ),
    ]


def _strip_dashdash(rest: list[str]) -> list[str]:
    return rest[1:] if rest[:1] == ["--"] else rest


def _is_connect_opt(tok: str) -> bool:
    return tok in ("-C", "--connect") or tok.startswith(("--connect=", "-C"))


def normalize_passthrough_argv(argv: list[str]) -> list[str]:
    """Make `otto ceph -s` work: argparse REMAINDER rejects a leading '-' argument."""
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in ("-C", "--connect"):
            i += 2
            continue
        if _is_connect_opt(tok) or tok == "--allow-fsid-mismatch":
            i += 1
            continue
        if tok.startswith("-") or tok not in ("ceph", "exec"):
            return argv
        rest = argv[i + 1 :]
        # `otto exec --help` is a question for otto; `otto ceph --help` stays ceph's
        if rest[:1] == ["--"] or (tok == "exec" and rest[:1] in (["-h"], ["--help"])):
            return argv
        if rest and _is_connect_opt(rest[0]):
            _fail(
                f"put -C/--connect before the subcommand: otto {rest[0]} ... {tok} ...; "
                f"after '{tok}' it would be passed to the command instead of selecting the connection"
            )
        return [*argv[: i + 1], "--", *rest]
    return argv


def _require_checked_cluster() -> None:
    """otto ceph / otto exec run only on a cluster whose fsid was just checked."""
    if "OTTO_ACTIVE_CONNECTION" not in os.environ:
        _fail(
            "no cluster selected, so there is no fsid to check; "
            "pick one with: otto use NAME (or for one command: otto -C NAME ...)"
        )


def _cmd_ceph(args) -> None:
    _require_checked_cluster()
    exe = shutil.which("ceph")
    if exe is None:
        _fail("the `ceph` CLI is not on PATH", 127)
    _run_passthrough([exe, *_strip_dashdash(args.rest)])


def _cmd_exec(args) -> None:
    argv = _strip_dashdash(args.rest)
    if not argv:
        _fail("usage: otto [-C CONNECTION] exec -- COMMAND [ARGS...]")
    _require_checked_cluster()
    _run_passthrough(argv)


def add_command_passthrough(subparsers) -> None:
    c = subparsers.add_parser(
        "ceph", help="Run a raw ceph command against the selected connection"
    )
    c.add_argument("rest", nargs=argparse.REMAINDER)
    c.set_defaults(func=_cmd_ceph)
    e = subparsers.add_parser(
        "exec",
        help="Run any command (rbd, rados, radosgw-admin, ...) against the selected connection",
        description="Run a command with CEPH_ARGS, CEPH_CONF and CEPH_KEYRING pointing "
        "at the selected connection, e.g.: otto -C prod exec rbd ls",
    )
    e.add_argument(
        "rest",
        nargs=argparse.REMAINDER,
        metavar="COMMAND",
        help="command and arguments",
    )
    e.set_defaults(func=_cmd_exec)
