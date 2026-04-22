# Release Checklist

This document outlines the steps to fully ship CodeAtlas after the initial v1.0.0 tag.

## Prerequisites

- All code committed and pushed to `main`
- CI passing on all commits
- Git tags updated to target release version (e.g., `v1.0.0`)
- Demo GIFs recorded and placed in `docs/assets/` (hero.gif, web-ui.gif)

## Step 1: PyPI Publish

Publish the Python package to PyPI (uses Trusted Publishing — no manual API tokens required if configured in GitHub repo settings).

```bash
# Generate distribution files
python -m build

# Publish (this will be auto-triggered by GitHub Actions on tag, or manual via):
twine upload dist/*
```

Or let the GitHub Actions CI/CD pipeline handle it (`python -m publish` via workflow).

## Step 2: Homebrew Tap

Once the PyPI package is live and the tarball is available at:
```
https://files.pythonhosted.org/packages/source/c/codeatlas/codeatlas-1.0.0.tar.gz
```

Compute the sha256 hash of the tarball and update the formula:

```bash
# Fetch the sdist and compute sha256
curl -sL https://files.pythonhosted.org/packages/source/c/codeatlas/codeatlas-1.0.0.tar.gz | shasum -a 256

# Copy the hash and update Formula/codeatlas.rb
# Replace: REPLACE_WITH_SDIST_SHA256_AFTER_PYPI_PUBLISH
# With: <paste the sha256 from above>
```

Create a Homebrew tap repository to host the formula:

```bash
# Create a new repo at GitHub: https://github.com/AryanSaini26/homebrew-tap
# Clone locally:
git clone https://github.com/AryanSaini26/homebrew-tap.git
cd homebrew-tap

# Create the formula directory:
mkdir -p Formula

# Copy the updated formula:
cp ../CodeAtlas/Formula/codeatlas.rb ./Formula/

# Commit and push:
git add Formula/codeatlas.rb
git commit -m "Add codeatlas formula"
git push origin main
```

Users can now install via:
```bash
brew tap AryanSaini26/homebrew-tap
brew install codeatlas
```

## Step 3: VS Code Extension Marketplace

The extension is compiled and packaged as `.vsix`. To publish:

```bash
cd vscode-extension

# Ensure it's built and packaged:
npm install
npm run compile
npm run package

# Publish to marketplace (requires being logged in as publisher "aryansaini26"):
npm run publish

# Or manually upload the .vsix file via https://marketplace.visualstudio.com/manage
```

## Step 4: Documentation & Launch

- Verify GH Pages docs are live at `https://aryansaini26.github.io/CodeAtlas/`
- Embed demo GIFs in README (replace placeholders in lines ~11-16, ~105-109)
- Post launch content:
  - HN: See `docs/launch-post.md` (HN body section)
  - Reddit: `r/programming`, `r/LocalLLaMA`, `r/ClaudeAI` (reuse HN body with subreddit-specific tone)
  - Twitter: Thread format in `docs/launch-post.md`
  - Blog (optional): Full blog post outline in `docs/launch-post.md`

## Verification

- [ ] `pip install codeatlas` succeeds
- [ ] `brew install AryanSaini26/homebrew-tap/codeatlas` succeeds
- [ ] `code --install-extension codeatlas-vscode-0.1.0.vsix` works
- [ ] GH Pages docs render correctly
- [ ] All 3 distribution channels (PyPI, Homebrew, VS Code Marketplace) list the same version

## Rollback

If any step fails:

1. **PyPI**: Files are immutable once published. Create a new version (1.0.1) with fixes.
2. **Homebrew**: Update the formula in the tap repo and push again.
3. **VS Code Marketplace**: Unpublish and re-publish with fixes.
4. **Docs**: Redeploy via GitHub Pages (automatic on push to main).

---

For questions, see `README.md` "Releasing" section and the GitHub Actions CI workflow.
