Changelog Keeper CLI
====================

A CLI tool that helps you with maintaining ``CHANGELOG.md`` using
`keep a changelog`__ format.

__ https://keepachangelog.com/


Features
--------

-  Tools for everyday changelog maintenance: bumping versions, checking consistency
   and release ordering, re-formatting markdown, automatically fixing errors.

-  Changelog Keeper uses a full-fledged Markdown parser, thus minimizing chances
   of mis-parses.

-  Flexible configuration with ``.changelog.yaml`` allows working with multitude
   of changelog styles and versioning schemas.

-  Analyzing project releases by inspecting git tags.

-  Generating links for each release section based on repository remotes
   and link templates.

-  Integration with :ref:`pre-commit hooks <pre-commit-usage>`
   and :ref:`GitHub CI routines <ci-usage>`.


Is this tool for me?
--------------------

Changelog Keeper is not a changelog generator; rather, it's a set of tools that
helps you with keeping a changelog.

This tool is for you if:

-  you prefer to write changelog yourself, but need help automating some tedious tasks
   (such as bumping releases and fixing release links);

-  you want to make sure that your changelog stays consistent, and that all of your
   release versions and git tags conform to the selected specification;

-  you want to parse changelog and extract data from it during automated
   release pipelines.

If you want to generate changelog from commit messages, though, this tool is not it.
We recommend using `git cliff`__ or something similar instead.

__ https://git-cliff.org/


Contents
--------

.. toctree::
   :maxdepth: 2

   installation
   usage
   config
   advanced

.. toctree::
    :hidden:
    :caption: Links

    GitHub <https://github.com/taminomara/cl-keeper>
