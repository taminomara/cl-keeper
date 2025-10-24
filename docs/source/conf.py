import datetime
import json

import sphinx.application
import sphinx.builders
import sphinx.builders.html
import yuio.json_schema

import cl_keeper
import cl_keeper.config

# -- Project information -----------------------------------------------------

project = "Changelog Keeper CLI"
copyright = f"{datetime.date.today().year}, Tamika Nomara"
author = "Tamika Nomara"
release = version = cl_keeper.__version__


# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.githubpages",
    "sphinx_design",
    "yuio.ext.sphinx",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
}
# nitpick_ignore_regex = [
#     (r"py:class", r"(.*\.)?([A-Z]{1,2}|[A-Z]+_co|Cmp|SupportsLt|Sz|TAst|_[^.]*)")
# ]
autodoc_typehints_format = "short"
autodoc_member_order = "bysource"
autodoc_inherit_docstrings = False

# -- Options for HTML output -------------------------------------------------

html_theme = "furo"
html_static_path = ["_static"]
html_css_files = ["extra.css"]
html_theme_options = {
    "source_repository": "https://github.com/taminomara/cl-keeper",
    "source_branch": "main",
    "source_directory": "docs/source",
}


def on_write_started(app: sphinx.application.Sphinx, builder):
    if not isinstance(builder, sphinx.builders.html.StandaloneHTMLBuilder):
        return

    ctx = yuio.json_schema.JsonSchemaContext()
    schema = yuio.json_schema.Meta(
        cl_keeper.config.Config.to_json_schema(ctx),
        title=cl_keeper.config.Config.__name__,
        description=cl_keeper.config.Config.__doc__,
    )
    app.outdir.joinpath("schema.json").write_text(
        json.dumps(
            ctx.render(
                schema, id="https://cl-keeper.readthedocs.io/en/latest/schema.json"
            ),
            indent=2,
        )
    )


def setup(app: sphinx.application.Sphinx):
    app.connect("write-started", on_write_started)

    return {
        "version": cl_keeper.__version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
