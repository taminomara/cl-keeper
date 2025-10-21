Config
======

.. currentmodule:: cl_keeper.config

Changelog Keeper searches for ``.changelog.yaml``, ``.changelog.toml``,
or ``pyproject.toml``. In ``pyproject.toml``, keeper's config is located under the
``tool.cl_keeper`` key.


Example
-------

.. tab-set::

    .. tab-item:: ``.changelog.yaml``

        .. code-block:: yaml

            version_format: python-semver
            tag_prefix: ""

    .. tab-item:: ``pyproject.toml``

        .. code-block:: toml

            [tool.cl_keeper]

            version_format = "python-semver"
            tag_prefix = ""


Full list of config keys
------------------------

.. autoconfig:: Config
    :members:
    :display-name: .changelog.yaml
    :show-flags:
    :flag-prefix: cfg


Link presets
------------

.. autoconfig:: ReleaseLinkPreset
    :members:
    :display-name: ReleaseLinkPreset


Supported version formats
-------------------------

.. autoconfig:: VersionFormat
    :members:
    :display-name: VersionFormat


List of issue codes
-------------------

.. autoconfig:: IssueCode
    :members:
    :display-name: IssueCode

.. autoconfig:: IssueSeverity
    :members:
    :display-name: IssueSeverity
    :enum-by-name:
    :enum-to-dash-case:
