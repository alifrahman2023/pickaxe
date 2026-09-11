# CI parity and reproducible benchmarks only — never the shipping vehicle
# (context/notes.md §7, §14). Keep repos in a named volume, not a bind mount:
# Docker Desktop's host filesystem translation is catastrophic for a workload
# that reads hundreds of thousands of git objects.
FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake ninja-build git ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

# hyperfine is not reliably in Ubuntu's default repos; take the released .deb.
ARG HYPERFINE=1.18.0
RUN arch="$(dpkg --print-architecture)" \
 && curl -fsSL -o /tmp/hf.deb \
      "https://github.com/sharkdp/hyperfine/releases/download/v${HYPERFINE}/hyperfine_${HYPERFINE}_${arch}.deb" \
 && dpkg -i /tmp/hf.deb && rm /tmp/hf.deb

WORKDIR /work
