# This dockerfile will build copilot intto a single binary when run.
# It will require the repository to be mounted as a volume into '/app'.
# The resulting ceph-copilot binary will be available at './dist'.
#
# A CentOS 8 image is chosen purely because it has a lower glibc version,
# thus a potentially broader reach.
FROM centos:8

# Fix mirrors since CentOS 8 is EOL
RUN sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-* && \
  sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-*

RUN yum install -y git
WORKDIR /app

# Make build script executable and run it
SHELL [ "/bin/bash", "-o", "pipefail", "-c" ]
RUN curl -LsSf https://astral.sh/uv/install.sh | \
  UV_INSTALL_DIR=/usr/bin \
  UV_DISABLE_UPDATE=1 \
  UV_NO_MODIFY_PATH=1 \
  /bin/sh

VOLUME [ "/app" ]
ENTRYPOINT [ "/app/build.sh" ]
