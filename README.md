# s2-self-certification

<div align="center">
    <a href="https://s2standard.org"><img src="./Logo-S2.svg" width="200" height="200" /></a>
</div>
<br />

## Getting started

## Development

Currently this repository uses a custom version of the S2-Python library. It is in this repository as a Git Submodule. In order to clone the repo with the submodule please run:

```bash
git submodule init
git submodule update --remote --merge
```

### Executing with Hot Reload

```bash
watchmedo auto-restart --pattern "*.py" --recursive --signal SIGTERM python ./src/s2-self-certification/main.py ./src/s2-self-certification/config.yaml
```
