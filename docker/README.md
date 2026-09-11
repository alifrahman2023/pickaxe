# Docker

Build environment for CI parity and benchmarks. Not a deployment vehicle: container
startup is 100-500 ms against a 30 ms query budget, and the tool needs the user's
filesystem.

```sh
docker build -t pk-dev docker/
docker run --rm -it -v pk-cache:/work pk-dev
```

Clone the repos you benchmark against *inside* the container or into the named volume.
A bind-mounted host path goes through Docker Desktop's filesystem translation layer and
will dominate every measurement.
