# Ceph Copilot

Ceph Copilot is a CLI assistant designed to help administrators manage their
Ceph clusters more efficiently. The tool provides a variety of features to help
validate cluster health, simplify complex maintenance tasks, and optimize
configurations for improved performance and stability.

## Features

**Cluster Validation**: Ceph Copilot checks the health of your Ceph cluster and
validates its configuration to ensure optimal performance and reliability.

- **Advanced Monitoring and Advising**: Future versions of Ceph Copilot will
  include agents that monitor OSDs, MDSs, RGWs, and other cluster daemons,
  providing real-time insights and advice for improved configurations.

## Getting Started

## Development Guide

This repository contains not only Ceph Copilot, but also a few other related
utilities. The repository is organized in the following fashion:

- `copilot/`, containing the Copilot library
- `copilot/src/clyso/ceph/copilot/`, containing the Ceph Copilot utility

### Prerequisites

Before starting development, please ensure the you have the following
prerequisites present in your system:

- Python 3.11 or later
- The [`uv`][_uv_url] package manager

Additionally, a working Ceph cluster will be required for Copilot, and related
utilities, to work. Please refer to the [Ceph Documentation][_ceph_docs_url] on
how to achieve this.

[_uv_url]: https://docs.astral.sh/uv
[_ceph_docs_url]: https://docs.ceph.com

### Setup Development Environment

At the root of the repository, run the following:

```bash
uv venv
source .venv/bin/activate
uv sync --all-packages
```

This will initiate a virtual environment for the workspace, and install all the
required dependencies (including development dependencies).

If you want to only install dependencies for the CLI tool itself, you can run:

```bash
uv pip install ./copilot
```

Please refer to the [`uv` documentation][_uv_url] for insights on how to perform
common operations with `uv`, such as adding or removing packages, etc.

### Linting and Formatting

For development it is recommended to do `uv sync --all-packages` as this will
install lefthook and ruff.

lefthook is used to run pre-commit hooks ruff is used to lint and format the
code

To run the pre-commit hooks manually, run:

```bash
lefthook run pre-commit
```

more information on what gets ran can be found in the
[.lefthook.yaml](.lefthook.yaml) file or `lefthook dump` command.

To automatically format the code, run:

```bash
ruff format
```

### Building the Ceph Copilot's Python Binary

To build a compatible binary that works on CentOS 8 and other systems with older
glibc versions, follow these steps:

1. Build the Docker image:

```bash
docker build -f pyinstaller.Dockerfile -t ceph-copilot-builder .
```

<!-- markdownlint-disable MD029 -->

2. Run the container against the current repository:

```bash
docker run -v .:/app ceph-copilot-builder:latest
```

<!-- markdownlint-enable -->

The binary will be available in the repository's `dist/` directory.

Alternatively, the `build.sh` script can be run. This script will, by default,
build the binary using the developer's local environment. If building with a
container is preferred, running `./build.sh --container` will ensure the entire
build is performed as described in the previous steps.

#### Verifying the Binary

```bash
dist/ceph-copilot --version
dist/ceph-copilot --help
```

### Running Ceph Copilot's related utilities

The various utilities shipped in this repository can be run in two distinct
ways:

- Manually, using the developer's local virtual environment
- By building a container image with the required packages

For manual instructions, please refer to the utility's README file.

To build the container image, please run the following from the repository's
root:

```bash
docker build -f <utility-dir>/Dockerfile -t my-container-image .
docker run [options] my-container-image:latest
```

For `options` required for each utility, please refer to the utility's README
file.

### Using `podman` instead of `docker`

Keep in mind that using rootless `podman` may require certain flags to be
enabled when running the containers, especially relevant if volume mounts are
used. If you run into problems, please consider using `--userns keep-id` and
`--security-opt label=disable`.

### Running tests

To run the tests in this repository, please run the following:

```bash
source .venv/bin/activate
python3 -m unittest discover tests
```

## Usage example

Usage example: Analyze your cluster `ceph report` for best practices and known
issues:

<!-- markdownlint-disable MD013 -->

```shell
$ ceph-copilot cluster checkup --ceph_report_json=tests/reports/08.json
Running tests: .!XX...X.!!.....X..............!X..

Overall score: 28 out of 35 (F)

- WARN in Version/Major Release: Not running the recommended major release quincy v17
- FAIL in Version/Minor Release: Not running the recommended minor bugfix release for pacific
- FAIL in Version/Check for Known Issues in Running Version: CRITICAL: Found 1 high severity bugs(s) in running version 16.2.10
- FAIL in Pools/Recommended Flags: Some pools have missing flags
- WARN in Pools/Pool Autoscale Mode: pg_autoscaler is on which may cause unexpected data movement
- WARN in Pools/RBD Pools: Too many RBD pools
- FAIL in Pools/Pool Space Amplification: Some pools have high space amplification
- WARN in OSD Health/OSD host swap: All OSD hosts have swap enabled
- FAIL in OSD Health/Check number of osdmaps stored: Cluster has too many osdmaps (185437)

Use --verbose for details and recommendations
```

<!-- markdownlint-enable -->

### Testing rpm builds using podman

Assume podman is setup and works correctly. Being in the copilot source repo
run:

```bash
podman run -it --rm --arch x86_64 -v $PWD:/clyso:O rockylinux:9 bash
```

Enable required repos and install deps:

```bash
dnf install -y epel-release
dnf config-manager --enable crb
dnf install -y git rpm-build rpmdevtools python3-devel python3-setuptools
```

Try and build rpm

```bash
cd /clyso && ./build_rpm.sh $(git describe | cut -d - -f 1-1)
```

## Installation

Ceph Copilot comes in the form of a Python binary, and its latest version can be
downloaded directly [here][_copilot_download_url]. Alternatively, Ceph Copilot
comes in containerized form, and can be obtained from Clyso's container
registry, by running the following command:

```bash
docker pull harbor.clyso.com/ces/copilot/copilot:latest
```

[_copilot_download_url]: https://get.copilot.clyso.com

## Roadmap

Ceph Copilot is under active development, and future versions will include the
following features:

- Improved monitoring of OSDs, MDSs, RGWs, and other cluster daemons
- Real-time insights and advice for optimizing configurations
- Integration with popular alerting and monitoring platforms

## License

Ceph Copilot is licensed under the [XY License](LICENSE).

## Support and Community

For questions, bug reports, or feature requests, please open an issue on the
[GitHub repository](https://github.com/clyso/ceph-copilot/issues).
