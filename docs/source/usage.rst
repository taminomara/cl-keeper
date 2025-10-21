Usage
=====

.. currentmodule:: cl_keeper.config

Changelog Keeper's command is called  :program:`chk`. It comes with four main subcommands:

**chk check**
    checks contents of the changelog file.

**chk fix**
    fixes contents of the changelog file.

**chk bump**
    moves entries from the ``unreleased`` section to a new release.

**chk find**
    searches a changelog entry for the given release version.

All of them accept a few universal flags:

-c <file>, --config <file>
    Overrides path to the config file.

    By default, Changelog Keeper searches for ``.changelog.yaml``,
    ``.changelog.toml``, or ``pyproject.toml`` in the current directory
    or its parents.

    If :flag:`--input` is given, Changelog Keeper searches for config starting from the
    input file's directory instead.

    If config can't be found, Changelog Keeper will use the default config.

-i <path>, --input <path>
    Overrides path to the changelog file.

    By default, Changelog Keeper searches for config, then searches
    for ``CHANGELOG.md`` relative to the config file's directory.

    If config can't be found, Changelog Keeper searches for ``CHANGELOG.md`` in the
    current directory instead.

--strict
    Increases severity of all messages by one level.


Check
-----

.. code-block:: console

    $ chk check [<options>]

-   Checks changelog for any issues. Issue severities can be controlled by the
    :attr:`~Config.severity` config option.


Fix
---

.. code-block:: console

    $ chk fix [<options>]

-   Checks changelog for any issues, and fixes whichever issues it can. Issue
    severities can be controlled by the :attr:`~Config.severity` config option.

--dry-run
    Doesn't save changes. Instead, prints colored diff to ``stderr``.
    Implies :flag:`--diff`.

--diff
    Print diff for produced changes.


Bump
----

.. code-block:: console

    $ chk bump [<options>] [--ignore-errors] [--dry-run] [--edit] [--commit] <version>
    $ chk bump [<options>] [--ignore-errors] [--dry-run] [--edit] [--commit] [auto|major|minor|patch|post] [--alpha|--beta|--rc]

-   First form moves entries from the ``unreleased`` section to a new release
    for the specific version.
-   Second form does the same, but the new version number is generated based
    on the last release.

`<version>`:flag:
    Version for the new release. Can start with :attr:`~Config.tag_prefix`, in which case
    the prefix is stripped.

    If :flag:`<version>` is ``major``, ``minor``, ``patch``, or ``post``, this command
    bumps the corresponding component of the latest version.
    In this case, the latest version is determined by comparing all releases
    (and tags, if :attr:`~Config.check_repo_tags` is ``true``) with respect to the chosen
    :attr:`~Config.version_format`.

    If :flag:`<version>` is ``auto``, this command inspects third-level headings
    of the ``unreleased`` section to determine which version component to bump:

    -   if there is a ``breaking`` category, it creates a major release;
    -   if there are ``added``, ``changed``, or ``removed`` categories, it creates
        a minor release;
    -   if there are ``security``, ``deprecated``, ``performance``, or ``fixed``
        categories, it creates a patch release;
    -   if none of the above categories are present, the command fails.

    The list of categories for automatic bumping can be adjusted, see config options
    :attr:`~Config.bump_patch_categories`, :attr:`~Config.bump_minor_categories`,
    :attr:`~Config.bump_major_categories`.

--alpha, --beta, --rc
    These flags affect automatic bumping to create a pre-release.

    These options are only allowed if :flag:`<version>` is ``auto``, ``major``,
    ``minor``, ``patch``, or ``post``, or if :flag:`<version>` is not given at all.
    In the later case, the previous release should itself be a pre-release.

--ignore-errors
    Produces result even if errors are detected.

--dry-run
    Doesn't save changes. Instead, prints colored diff to ``stderr``.

--edit
    Opens an editor and allows changing contents of the new release section
    before saving changes.

--commit
    Commit and tag the new release. Changelog Keeper will pause before committing
    and allow you to inspect repository or cancel the commit.


**Examples:**

Create release ``1.0.5``:

.. code-block:: console

    $ chk bump 1.0.5

Determine new version automatically:

.. code-block:: console

    $ chk bump auto

Create a new minor release, i.e. ``1.0.0`` → ``1.1.0``:

.. code-block:: console

    $ chk bump minor

Create a beta pre-release for a major release, i.e. ``1.5.1`` → ``2.0.0-beta0``:

.. code-block:: console

    $ chk bump major --beta

Bump last pre-release:

.. code-block:: console

    $ chk bump --beta

Examples of pre-release bumping:

- ``1.0.0-beta0`` → ``1.0.0-beta1``;
- ``1.0.0-alpha2`` → ``1.0.0-beta0``;
- ``1.0.0`` → error: ``1.0.0-beta0`` can't be released after ``1.0.0``;
- ``1.0.0-rc0`` → error: ``1.0.0-beta0`` can't be released after ``1.0.0-rc0``.


Find
----

.. code-block:: console

    $ chk find [<options>] [--ignore-errors] [--json] <version>
    $ chk find [<options>] [--ignore-errors] [--json] unreleased
    $ chk find [<options>] [--ignore-errors] [--json] latest

-   First form prints a changelog entry for the given release version.
-   Second form prints contents of the unreleased section.
-   Third form scans the changelog file and prints contents of the top-most
    non-``unreleased`` entry.

If errors detected in the changelog, the command fails unless :flag:`--ignore-errors`
was given.

If changelog entry isn't found, the requested version is searched in the repo tags.
If it's found in the repo, and it satisfies :attr:`~Config.ignore_missing_releases_before`
or :attr:`~Config.ignore_missing_releases_regexp`, an empty result is printed.

`<version>`:flag:
    Version that will be extracted from the changelog. Can start with
    :attr:`~Config.tag_prefix`, in which case the prefix is stripped.

    If :flag:`<version>` is ``unreleased``, the command prints contents
    of the unreleased section.

    If :flag:`<version>` is ``latest``, the command prints contents of the top-most
    non-``unreleased`` entry.

--ignore-errors
    Produces result even if errors are detected.

--json
    Prints data as JSON object with the following keys:

    ``version``
        version string, as appears in the changelog.

        Can be ``null`` if unreleased section is requested.

    ``canonizedVersion``
        version string, canonized according to the used :attr:`~Config.version_format`.

        If :attr:`~Config.version_format` is ``null`` or canonization fails,
        this will contain string from ``version``.

    ``tag``
        tag that corresponds to this version.

        Can be ``null`` if requested release not found, if unreleased section
        is requested, if :attr:`~Config.check_repo_tags` is ``false``, if version canonization
        fails, or if tag is not found for this release.

    ``text``
        text extracted from the changelog entry.

        Can be empty if requested release not found.

    ``isLatestInChangelog``
        ``true`` if found version appears first in the changelog file.

        Can be ``null`` if requested release not found, or if unreleased section
        is requested.

    ``isLatestInSemanticOrder``
        ``true`` if this is the latest known release.

        Release versions are compared with respect to the selected
        :attr:`~Config.version_format`. If :attr:`~Config.check_repo_tags` is ``true``, this option
        also checks all tags found in the repository.

        Can be ``null`` if requested release not found, or if unreleased section
        is requested.

    ``isPreRelease``
        ``true`` if release version contains a pre-release component,
        like ``beta`` or ``rc``.

        Can be ``null`` if requested release not found, if unreleased section
        is requested, or if version canonization fails.

    ``isPostRelease``
        ``true`` if release version contains a post-release component.

        Can be ``null`` if requested release not found, if unreleased section
        is requested, or if version canonization fails.

    ``isUnreleased``
        ``true`` if unreleased section is requested.
