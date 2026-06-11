import sys
import os
import shutil
import pathlib

sys.path.insert(0, os.path.abspath(".."))

project = "vorpal"
copyright = "2026, vorpal contributors"
author = "vorpal contributors"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_nb",
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]

html_theme = "furo"
html_static_path = ["_static"]
html_title = "vorpal"

html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#5c2d91",
        "color-brand-content": "#5c2d91",
    },
    "dark_css_variables": {
        "color-brand-primary": "#c39bd3",
        "color-brand-content": "#c39bd3",
    },
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
}

html_css_files = ["wonderland.css"]

# Mock heavy optional imports so autodoc works without a GPU environment
autodoc_mock_imports = [
    "torch", "kokoro", "misaki", "transformers",
    "cv2", "soundfile", "scipy", "anthropic",
    "fastapi", "uvicorn", "httpx",
]

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

# myst-nb: render stored outputs, never re-execute notebooks
nb_execution_mode = "off"
nb_execution_timeout = 0

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Copy notebooks from ../notebooks/ into sphinx/notebooks/ at build time
def copy_notebooks(app):
    src = pathlib.Path(app.srcdir).parent / "notebooks"
    dst = pathlib.Path(app.srcdir) / "notebooks"
    if src.exists():
        dst.mkdir(exist_ok=True)
        for nb in sorted(src.glob("*.ipynb")):
            shutil.copy2(nb, dst / nb.name)


def setup(app):
    app.connect("builder-inited", copy_notebooks)
