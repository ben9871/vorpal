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

html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#1a7a78",
        "color-brand-content": "#1a7a78",
    },
    "dark_css_variables": {
        "color-brand-primary": "#2ea8a5",
        "color-brand-content": "#2ea8a5",
    },
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    "top_of_page_buttons": ["view"],
}

html_css_files = ["wonderland.css"]

html_sidebars = {
    "**": [
        "sidebar/brand.html",
        "sidebar/search.html",
        "sidebar/scroll-start.html",
        "sidebar/navigation.html",
        "sidebar/scroll-end.html",
    ]
}

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
