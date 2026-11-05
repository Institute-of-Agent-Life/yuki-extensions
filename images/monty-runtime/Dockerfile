ARG RUST_IMAGE=docker.io/library/rust@sha256:811d6caab4a84e6148c8722128993c1caf152156868b2b66f3a26af189b0dad8
ARG UV_IMAGE=ghcr.io/astral-sh/uv@sha256:812f4717f0002c1c5400653454de9a29b7cbe93bdfe19451376d6aaac522a9bf
ARG PYTHON_IMAGE=docker.io/library/python@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b
# Offline validation/build image. It does not start a Bot, gateway or Manager.
FROM ${RUST_IMAGE} AS rust
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS monty
COPY --from=rust /usr/local/cargo /usr/local/cargo
COPY --from=rust /usr/local/rustup /usr/local/rustup
COPY --from=uv /uv /uvx /bin/
ENV CARGO_HOME=/usr/local/cargo RUSTUP_HOME=/usr/local/rustup \
    PATH="/usr/local/cargo/bin:$PATH" CARGO_BUILD_JOBS=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git gcc libc6-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY scripts/build_monty_distribution.sh /build/scripts/
COPY vendor/patches /build/vendor/patches
COPY vendor/monty/launcher.c /build/vendor/monty/launcher.c
COPY inputs/monty.git /inputs/monty.git
RUN git config --global url.file:///inputs/monty.git.insteadOf https://github.com/pydantic/monty.git
ENV CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16 CARGO_PROFILE_RELEASE_LTO=false
RUN bash /build/scripts/build_monty_distribution.sh /build/distribution /usr/local/bin/python build
COPY scripts/export_monty_notices.py /build/scripts/
RUN bash /build/scripts/build_monty_distribution.sh /build/distribution /usr/local/bin/python notices

FROM ${PYTHON_IMAGE} AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 validator \
    && useradd --uid 10001 --gid validator --no-create-home validator
COPY --from=monty /build/distribution/monty/target/release/monty /opt/yuki-monty/monty
COPY --from=monty /build/distribution/monty-isolated /opt/yuki-monty/monty-isolated
COPY --from=monty /build/distribution/wheels /opt/yuki-monty/wheels
COPY --from=monty /build/distribution/THIRD_PARTY_NOTICES.json /opt/yuki-monty/THIRD_PARTY_NOTICES.json
COPY --from=monty /build/distribution/artifacts.json /opt/yuki-monty/artifacts.json
COPY LICENSE /opt/yuki-monty/licenses/Yuki-LICENSE
COPY vendor/monty/LICENSE /opt/yuki-monty/licenses/Monty-LICENSE
COPY vendor/monty/TYPESHED-LICENSE /opt/yuki-monty/licenses/TYPESHED-LICENSE
COPY deploy/security/MOBY-PROFILES-LICENSE /opt/yuki-monty/licenses/MOBY-PROFILES-LICENSE
COPY scripts/verify_monty_isolation.py /opt/yuki-monty/verify_monty_isolation.py
# The small validation image does not install Yuki's uv.lock environment.
# Preserve the binding's required typing-extensions dependency using the exact
# version/wheel hash already locked there; never resolve a floating dependency.
RUN pip install --no-deps --disable-pip-version-check \
    'https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl#sha256=481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8' \
    /opt/yuki-monty/wheels/*.whl
COPY backend /opt/yuki-monty/backend
ENV PYTHONPATH=/opt/yuki-monty/backend
RUN python /opt/yuki-monty/backend/make_contract.py
RUN chmod -R u=rwX,go=rX /opt/yuki-monty
USER 10001:10001
WORKDIR /tmp
LABEL org.opencontainers.image.title="Yuki Monty runtime" org.opencontainers.image.version="0.1.0-alpha.1"
ENTRYPOINT ["python", "/opt/yuki-monty/backend/bridge.py"]
