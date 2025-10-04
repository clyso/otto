# Development Guide

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv) package manager
- A Ceph cluster (see [Ceph docs](https://docs.ceph.com))

## Setup

```bash
uv venv
source .venv/bin/activate
uv sync --all-packages
```

The CLI tool changes should be reflected when editing the code while being inside the python virtual environment.
This installs all dependencies including dev tools (lefthook, ruff).

To install only the Otto package:

```bash
uv pip install ./otto
```

uv can be dropped and use pip instead for installing.

## Code Quality

### Pre-commit hooks

Lefthook runs ruff on commit. To run manually:

```bash
lefthook run pre-commit
```

See `.lefthook.yaml` for what runs, or use `lefthook dump`.

### Format and Linting code

Check and fix linting issues automatically:

```bash
ruff check
ruff check --fix .
```

For formatting issues:
```bash
ruff format --check .
ruff format
```

Ruff follows the rules listed in `pyproject.toml` under `[tool.ruff.lint]` and runs on every PR.

## Building

### Binary

Pyinstaller is used to make this CLI usable as a single binary. `build.sh` can be used to build into a single binary. `--container` flag can be used
to make sure that the binary is useable on most linux systems. 

This is not a static binary as the CLI still dynamically links against system libraries such as glibc. Pyinstaller bundles the python interpreter + dependencies into a single binary.
To be compatible with most ceph deployments centos8 was used purely because it has a lower glibc (2.28) version, other images could have been used and may be used to be compatible with older distributions.

```bash
ldd otto
	linux-vdso.so.1 (0x00007ffebbb34000)
	libdl.so.2 => /lib/x86_64-linux-gnu/libdl.so.2 (0x00007f06da360000)
	libz.so.1 => /lib/x86_64-linux-gnu/libz.so.1 (0x00007f06da344000)
	libpthread.so.0 => /lib/x86_64-linux-gnu/libpthread.so.0 (0x00007f06da33f000)
	libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f06da116000)
	/lib64/ld-linux-x86-64.so.2 (0x00007f06da379000)
```

The one to note here is libc.so.6. This binary will only run on systems with glibc 2.28 or newer and x86_64.
Other binaries can be built as needed, feel free to open an issue about this topic.

### Development how to build
Build a binary:

```bash
./build.sh
```

Recommended to use --container to not use host system libraries. This assumes docker/podman installed.

```bash
./build.sh --container
```
Binary output: `dist/otto`

Verify:

```bash
dist/otto --version
dist/otto --help
```

### RPM package

```bash
./build_rpm.sh $(git describe | cut -d - -f 1-1)
```

### Testing RPM in container

```bash
docker run -it --rm -v $PWD:/clyso rockylinux:9 bash
```

Inside container:

```bash
dnf install -y epel-release
dnf config-manager --enable crb
dnf install -y git rpm-build rpmdevtools python3-devel python3-setuptools
git config --global --add safe.directory /clyso
curl -LsSf https://astral.sh/uv/install.sh | sh
cd /clyso && ./build_rpm.sh $(git describe | cut -d - -f 1-1)
```

## Testing

```bash
source .venv/bin/activate
python3 -m unittest discover tests
```

Or use the script:

```bash
./run_tests.sh
```
