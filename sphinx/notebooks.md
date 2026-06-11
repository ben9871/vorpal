# Notebooks

Interactive Jupyter notebooks covering the most common vorpal workflows.
Find them in the `notebooks/` directory.

| Notebook | What it covers |
|----------|----------------|
| [`01_first_audiobook.ipynb`](../notebooks/01_first_audiobook.ipynb) | Build your first audiobook end-to-end from a Gutenberg EPUB |
| [`02_voices.ipynb`](../notebooks/02_voices.ipynb) | Explore the voice suite, blend voices, and audition workflow |
| [`03_manifest_and_pipeline.ipynb`](../notebooks/03_manifest_and_pipeline.ipynb) | Inspect the manifest, understand stage caching, edit `book.json` |
| [`04_theatrical_plays.ipynb`](../notebooks/04_theatrical_plays.ipynb) | Build multi-voice audiobooks from stage plays |
| [`05_advanced_options.ipynb`](../notebooks/05_advanced_options.ipynb) | Draft mode, ASR quality check, pronunciation lexicon, loudness profiles |
| [`06_library_mode.ipynb`](../notebooks/06_library_mode.ipynb) | Batch-build a shelf of books with `vorpal library` |

## Running the notebooks

```bash
pip install jupyter
cd notebooks/
jupyter notebook
```

All notebooks assume vorpal is installed in the active environment
(`pip install -e .` from the repo root). See {doc}`getting_started` for setup.
