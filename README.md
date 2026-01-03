# ChangeLog Keeper

A CLI tool that helps you with maintaining `CHANGELOG.md`
using [keep a changelog] format.

## Resources

- [Documentation](https://cl-keeper.readthedocs.io/)
- [Issues](https://github.com/taminomara/cl-keeper/issues)
- [Source](https://github.com/taminomara/cl-keeper/)
- [PyPi](https://pypi.org/project/cl-keeper/)
- [Changelog](https://github.com/taminomara/cl-keeper/blob/main/CHANGELOG.md)

## GitHub action quickstart

Use `taminomara/cl-keeper@v1` to parse a change log. It takes git tag
(parameter `version`) and returns `text` and other release info.
See details in [documentation][GitHub Action].

**Example:**

```yaml
name: Create a release
  on:
    push:
      tags:
        - 'v*'
jobs:
  release:
    - name: Checkout source
      uses: actions/checkout@v4
    - id: changelog
      name: Parse Changelog
      uses: taminomara/cl-keeper@v1
      with:
        version: ${{ github.ref }}
    - name: Create GitHub release
      uses: softprops/action-gh-release@v2
      with:
        prerelease: ${{ fromJSON(steps.changelog.outputs.is-pre-release) }}
        draft: ${{ fromJSON(steps.changelog.outputs.is-unreleased) }}
        body: |
          ## Changelog

          ${{ steps.changelog.outputs.text }}
```

## Installation

Install [via pipx][pipx-install]:

```sh
pipx install cl-keeper
```

[GitHub Action]: https://cl-keeper.readthedocs.io/en/stable/advanced.html#using-changelog-keeper-in-github-actions
[keep a changelog]: https://keepachangelog.com/
[pipx-install]: https://cl-keeper.readthedocs.io/en/stable/installation.html#with-pipx
