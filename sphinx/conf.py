import sys
import os

sys.path.insert(0, os.path.abspath(".."))

project = "vorpal"
copyright = "2026, vorpal contributors"
author = "vorpal contributors"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]

html_theme = "furo"
html_static_path = ["_static"]
html_title = "vorpal"

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "special-members": "__init__",
}
autodoc_typehints = "description"

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True

myst_enable_extensions = ["colon_fence", "deflist"]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}
