Installation
============

With PipX
---------

Install PipX_, then install ``cl-keeper``:

.. code-block:: console

    sh$ pipx install cl-keeper

.. _PipX: https://pipx.pypa.io/stable/


With Pip
--------

If you develop a python project, you can list ``cl-keeper`` as your development
dependency in ``pyproject.toml``:

.. code-block:: toml

    [dependency-groups]
    dev = [
        "cl-keeper~=1.0",
    ]

Python 3.12 or higher is required.


With pre-commit
---------------

`Pre-commit`_ can download and install ``cl-keeper`` on its own.
See :ref:`pre-commit-usage` for details.

.. _Pre-commit: https://pre-commit.com/


Pre-compiled binaries
---------------------

You can download pre-compiled binaries from the releases_ page.

.. _releases: https://github.com/taminomara/cl-keeper/releases


Setting up autocompletion
-------------------------

Changelog keeper comes with pre-completion scripts for bash, zsh and fish. To install
them, simply run:

.. code-block:: console

    chk --completions
