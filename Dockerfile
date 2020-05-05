FROM ubuntu:18.04
LABEL maintainer="iphydf@gmail.com"

RUN apt-get update \
 && apt-get install --no-install-recommends -y \
 ca-certificates \
 cmake \
 cython3 \
 gcc \
 g++ \
 git \
 libopus-dev \
 libsodium-dev \
 libvpx-dev \
 pkg-config \
 python3-dev \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN git clone https://github.com/TokTok/c-toxcore /build/c-toxcore \
 && cmake -B/build/c-toxcore/_build -H/build/c-toxcore -DBOOTSTRAP_DAEMON=OFF -DMUST_BUILD_TOXAV=ON \
 && make -C/build/c-toxcore/_build install -j"$(nproc)" \
 && rm -r /build

RUN ldconfig

RUN groupadd -r -g 1000 builder \
 && useradd --no-log-init -r -g builder -u 1000 builder \
 && mkdir -p /home/builder/build \
 && chown -R builder:builder /home/builder
USER builder

WORKDIR /home/builder/build
COPY --chown=builder:builder pytox.ld setup.py /home/builder/build/
COPY --chown=builder:builder pytox /home/builder/build/pytox/
RUN python3 setup.py install --user \
 && rm -r /home/builder/build/*

COPY --chown=builder:builder tests /home/builder/build/tests/
RUN python3 tests/tests.py
