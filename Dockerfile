# syntax=docker/dockerfile:1
#
# CVV is a continuous verification visualizer.
#
# Multi-tool image:
#   * Ubuntu 24.04 base (Python 3.12)
#   * Django 5.2 LTS (see requirements.txt)
#   * PostgreSQL server/client from the PGDG repository.
#
# The PostgreSQL major version is a build argument so the same Dockerfile can
# produce images for e.g. PostgreSQL 12 and 18:
#
#   docker build --build-arg PG_VERSION=18 -t cv:pg18 .
#   docker build --build-arg PG_VERSION=12 -t cv:pg12 .
#
FROM ubuntu:24.04

ARG PG_VERSION=18

ENV DEBIAN_FRONTEND=noninteractive \
    PG_VERSION=${PG_VERSION} \
    PG_CLUSTER=main \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

# -------------------------------
# System dependencies
# -------------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common \
        build-essential \
        ca-certificates \
        curl \
        gnupg \
        git \
        gettext \
        graphviz \
        libpq-dev \
        postgresql-common \
        python3-dev \
        python3-pip \
        python3-setuptools \
        python3-wheel \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------
# PostgreSQL server + client of the requested major version (PGDG).
# Supports old and new majors side by side, e.g. 12 and 18.
# -------------------------------
RUN /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y && \
    apt-get install -y --no-install-recommends \
        postgresql-${PG_VERSION} \
        postgresql-client-${PG_VERSION} \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------
# Python dependencies in an isolated virtualenv
# -------------------------------
RUN python3 -m venv "${VIRTUAL_ENV}" && \
    pip install --no-cache-dir --upgrade pip

WORKDIR /cvv

COPY requirements.txt /cvv/requirements.txt
RUN pip install --no-cache-dir -r /cvv/requirements.txt

# -------------------------------
# Application sources + initial database deployment
# -------------------------------
COPY . /cvv
RUN chmod +x /cvv/deploys/*.sh /cvv/start.sh /cvv/stop.sh && \
    deploys/deployment.sh cvdb

# -------------------------------
# Expose default CVV port
# -------------------------------
EXPOSE 8989

ENTRYPOINT ["/cvv/deploys/entrypoint.sh"]
