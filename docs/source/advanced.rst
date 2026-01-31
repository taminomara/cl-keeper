Advanced usage
==============

.. currentmodule:: cl_keeper.config

.. _pre-commit-usage:

Using Changelog Keeper in pre-commit hooks
------------------------------------------

Changelog Keeper integrates with `pre-commit`_ tool. Add ``taminomara/cl-keeper``
to your ``.pre-commit-config.yaml``:

.. _pre-commit: https://pre-commit.com/

.. code-block:: yaml

    - repo: https://github.com/taminomara/cl-keeper
      rev: v1
      hooks:
        - id: clk
        - id: clk-tags

Then run `pre-commit autoupdate` to replace `v1` with the exact latest version:

.. code-block:: console

    $ pre-commit autoupdate

There are two hooks available:

**clk**
    runs :cli:cmd:`clk fix` on your repository.

**clk-tags**
    runs :cli:cmd:`clk check-tag` before push to check whether pushed tags conform to the selected
    :cli:field:`.version_format`.

    Note that there is no guarantee that this hook will catch all push attempts;
    it's best to run :cli:cmd:`clk check-tag` in CI as well.


.. _ci-usage:

Using Changelog Keeper in GitHub Actions
----------------------------------------

Changelog Keeper provides a GitHub action to extract release notes for the given tag.

Here's an example of using ``taminomara/cl-keeper@v1`` in combination with
``softprops/action-gh-release@v2`` to create a GitHub release on tag push:

.. code-block:: yaml

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

.. note::

    If you're running action in strict mode, you may need to enable full history fetch
    in order to validate git tags. Use ``fetch-depth`` for this:

    .. code-block:: yaml

        - name: Checkout source
          uses: actions/checkout@v4
          with:
            fetch-depth: 0

.. list-table:: Inputs
    :header-rows: 1
    :stub-columns: 1
    :widths: 20 10 10 60
    :name: gh-action-inputs

    * - Parameter
      - Type
      - Default
      - Description
    * - ``config``
      - ``string``
      - ``""``
      - Path to the config file, relative to repository root.
    * - ``changelog``
      - ``string``
      - ``""``
      - Path to the changelog file, relative to repository root.
    * - ``version``
      - ``string``
      - ``"latest"``
      - Version to search for, default is "latest".
    * - ``strict``
      - ``boolean``
      - ``false``
      - Run changelog keeper in strict mode.
    * - ``ignore-errors``
      - ``boolean``
      - ``false``
      - Ignore issues found in changelog.

.. list-table:: Outputs
    :header-rows: 1
    :stub-columns: 1
    :widths: 20 10 70
    :name: gh-action-outputs

    * - Output
      - Type
      - Description
    * - ``text``
      - ``string``
      - Extracted markdown text.
    * - ``is-latest``
      - ``boolean``\ [1]_
      - Indicates that this is the latest release so far.
    * - ``is-pre-release``
      - ``boolean``\ [1]_
      - Indicates that this is a pre-release.
    * - ``is-post-release``
      - ``boolean``\ [1]_
      - Indicates that this is a post-release.
    * - ``is-unreleased``
      - ``boolean``\ [1]_
      - Indicates that action returned an unreleased section of changelog.
    * - ``data``
      - ``object``\ [1]_
      - Full JSON output of the "clk find" command.

.. [1] GitHub actions encode all non-string outputs as JSON. Make sure to use
       ``fromJSON`` function on it.


Running Changelog Keeper from VSCode
------------------------------------

You can configure VSCode to run :cli:cmd:`clk fix` on the current file:

1.  Open :guilabel:`Tasks: Open User Tasks`.

2.  Add the following task:

    .. code-block:: json

        {
          "label": "clk",
          "type": "shell",
          "command": "clk fix -i '${file}' -m",
          "problemMatcher": {
            "fileLocation": "absolute",
            "source": "clk",
            "owner": "changelog-keeper",
            "applyTo": "allDocuments",
            "pattern": {
              "regexp": "^(.*):(\\d*):([a-zA-Z0-9 ]*):([a-zA-Z0-9 ]*):(.*)$",
              "file": 1,
              "line": 2,
              "severity": 3,
              "code": 4,
              "message": 5
            }
          },
          "presentation": {
            "echo": true,
            "reveal": "never",
            "focus": false,
            "panel": "shared",
            "showReuseMessage": true,
            "clear": false
          }
        }

3.  Now you can run :cli:cmd:`clk fix` using :guilabel:`Tasks: Run Task` command.
