Config
======

.. currentmodule:: cl_keeper.config

Changelog Keeper searches for ``.cl-keeper.yaml``, ``.cl-keeper.toml``,
or ``pyproject.toml``. In ``pyproject.toml``, keeper's config is located under the
``tool.cl_keeper`` key.


Examples
--------

Basic python config
~~~~~~~~~~~~~~~~~~~

.. tab-set::
    :sync-group: config-examples

    .. tab-item:: ``.cl-keeper.yaml``
        :sync: yaml

        .. code-block:: yaml

            # Default is `semver`; there's also `python` and `python-strict`.
            version_format: python-semver

            # Prefix for your git tags. Default is `v`.
            tag_prefix: ""

    .. tab-item:: ``pyproject.toml``
        :sync: pyproject.toml

        .. code-block:: toml

            [tool.cl_keeper]

            # Default is `python`; there's also `python-strict`.
            version_format = "python-semver"

            # Prefix for your git tags. Default is `v`.
            tag_prefix = ""

    .. tab-item:: Example changelog
        :sync: md

        .. code-block:: markdown

            # Changelog

            ## v1.5.1 - 2025-05-01

            ### Added

            - Added some feature.


Custom titles and decorations for change categories
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. tab-set::
    :sync-group: config-examples

    .. tab-item:: ``.cl-keeper.yaml``
        :sync: yaml

        .. code-block:: yaml

            change_categories:
              breaking: "💥 Breaking"
              security: "🔒 Security"
              added: "✨ Added"
              changed: "🔧 Changed"
              deprecated: "⚠️ Deprecated"
              removed: "🗑️ Removed"
              performance: "⚡ Performance"
              fixed: "🐛 Fixed"
            release_date_decorations: [" (", ")"]
            version_decorations: ["v", ""]

    .. tab-item:: Example changelog
        :sync: md

        .. code-block:: markdown

            # Changelog

            ## v1.5.1 (2025-05-01)

            ### ✨ Added

            - Added some feature.


Using item categories instead of sub-sections
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. tab-set::
    :sync-group: config-examples

    .. tab-item:: ``.cl-keeper.yaml``
        :sync: yaml

        .. code-block:: yaml

            # Disable change categories.
            change_categories: {}

            # Enable defaults for item categories.
            use_default_item_categories: true

    .. tab-item:: Example changelog
        :sync: md

        .. code-block:: markdown

            # Changelog

            ## v1.5.1 - 2025-05-01

            - [added] Added some feature.
            - [removed] Removed a deprecated feature.


Custom sub-sections with item categories
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. tab-set::
    :sync-group: config-examples

    .. tab-item:: ``.cl-keeper.yaml``
        :sync: yaml

        .. code-block:: yaml

            # Set custom categories.
            change_categories:
              frontend: Frontend
              api: Api
            # Enable defaults for item categories.
            use_default_item_categories: true
            # Set custom prefixes for item categories.
            item_categories:
              breaking: "💥 "
              security: "🔒 "
              added: "✨ "
              changed: "🔧 "
              deprecated: "⚠️ "
              removed: "🗑️ "
              performance: "⚡ "
              fixed: "🐛 "

    .. tab-item:: Example changelog
        :sync: md

        .. code-block:: markdown

            # Changelog

            ## v1.5.1 - 2025-05-01

            ### Frontend

            - ✨ Added some feature.

            ### Api

            - 🗑️ Removed deprecated interfaces.


Full list of config keys
------------------------

.. cli:autoobject:: cl_keeper.config.Config
    :name: config
    :display-name: .cl-keeper.yaml
    :flags:
    :flag-prefix: --cfg


Link presets
------------

.. cli:autoobject:: cl_keeper.config.ReleaseLinkPreset


Supported version formats
-------------------------

.. cli:autoobject:: cl_keeper.config.VersionFormat


List of issue codes
-------------------

.. cli:autoobject:: cl_keeper.config.IssueCode

.. cli:autoobject:: cl_keeper.config.IssueSeverity


Schema
------

If your IDE supports JSON schemas, config schema is available
at https://cl-keeper.readthedocs.io/en/stable/schema.json.

For example, to enable schema in VSCode, add the following comment to your config:

.. code-block:: yaml

    # yaml-language-server: $schema=https://cl-keeper.readthedocs.io/en/stable/schema.json
