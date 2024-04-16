# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))


# -- Project information -----------------------------------------------------

import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath("../../"))
import anchor  # noqa

project = "Anchor Annotator"
copyright = f"2021-{date.today().year}, Montreal Corpus Tools"
author = "Montreal Corpus Tools"

# The full version, including alpha/beta/rc tags
version = "0.5.0"
# The full version, including alpha/beta/rc tags.
release = "0.5"


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx_design",
    "sphinx.ext.viewcode",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.mathjax",
    "sphinx.ext.ifconfig",
    "sphinx.ext.autosummary",
    "numpydoc",
    "myst_parser",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]
source_suffix = [".rst", ".md"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "pydata_sphinx_theme"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]
html_css_files = [
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.3.0/css/all.min.css",
    "https://montreal-forced-aligner.readthedocs.io/en/latest/_static/css/mfa.css",
]

html_logo = "_static/anchor-yellow.svg"
html_favicon = "_static/favicon.ico"
default_role = "code"

html_theme_options = {
    "external_links": [
        {
            "url": "https://montreal-forced-aligner.readthedocs.io/",
            "name": "MFA docs",
        },
        {
            "url": "https://mfa-models.readthedocs.io/",
            "name": "Pretrained MFA models",
        },
    ],
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/MontrealCorpusTools/anchor-annotator",
            "icon": "fab fa-github",
        },
    ],
    "logo": {
        "text": "Anchor Annotator",
        # "image_dark": "logo-dark.svg",
    },
    "analytics": {
        "google_analytics_id": "G-VBJ8Y5QSF5",
    },
    "show_nav_level": 1,
    "navigation_depth": 4,
    "show_toc_level": 2,
    "collapse_navigation": False,
}
html_context = {
    # "github_url": "https://github.com", # or your GitHub Enterprise interprise
    "github_user": "MontrealCorpusTools",
    "github_repo": "Anchor-annotator",
    "github_version": "main",
    "doc_path": "docs/source",
}

html_sidebars = {"**": ["search-field.html", "sidebar-nav-bs.html", "sidebar-ethical-ads.html"]}
