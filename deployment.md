# 🚀 Deployment Guide

This document outlines the step-by-step instructions to deploy the `error` library to **PyPI** (so users can run `pip install error`) and set up the **GitHub Pages Shared Exception Viewer** (so error links resolve correctly).

---

## 📦 1. Publishing to PyPI

To make the package installable via `pip install error`, you need to package and upload it to PyPI.

### Prerequisites
Make sure you have `wheel` and `twine` installed:
```bash
.venv\Scripts\pip install setuptools wheel twine
```

### Steps to Publish
1.  **Build the Distribution Files**  
    Clean any previous builds and generate the source distribution (`sdist`) and build wheel (`bdist_wheel`):
    ```bash
    # Run from the root of c:\workspace\error
    .venv\Scripts\python setup.py sdist bdist_wheel
    ```
    This creates a `dist/` folder containing `.tar.gz` and `.whl` files.

2.  **Upload to TestPyPI (Recommended first)**  
    Upload your package to TestPyPI to verify it packages correctly without affecting the production index:
    ```bash
    .venv\Scripts\twine upload --repository testpypi dist/*
    ```

3.  **Upload to Production PyPI**  
    Once verified, upload the package to the official PyPI index:
    ```bash
    .venv\Scripts\twine upload dist/*
    ```
    *You will be prompted to enter your PyPI token credentials.*

---

## 🔗 2. Deploying the Shared Exception Viewer (GitHub Pages)

The error sharing link utility (`error.generate_share_link(exc)`) points to:
`https://happy-kumar-sharma.github.io/error/viewer.html`

To activate this viewer, you need to enable GitHub Pages on your repository:

### Steps to Deploy
1.  **Create your GitHub Repository**  
    Create a new repository on GitHub named `error` under your account (`Happy-Kumar-Sharma`):
    ```text
    https://github.com/Happy-Kumar-Sharma/error
    ```

2.  **Commit and Push Code**  
    Initialize git (if not done already), commit all files (including the `docs/` folder containing `viewer.html`), and push to GitHub:
    ```bash
    git init
    git add .
    git commit -m "feat: initial release of error library with docs viewer"
    git branch -M main
    git remote add origin https://github.com/Happy-Kumar-Sharma/error.git
    git push -u origin main
    ```

3.  **Enable GitHub Pages**  
    *   Open your browser and navigate to your repository: `https://github.com/Happy-Kumar-Sharma/error`.
    *   Click on **Settings** (gear icon in the top navigation bar).
    *   On the left sidebar, click on **Pages** (under the "Code and automation" section).
    *   Under **Build and deployment**, set **Source** to `Deploy from a branch`.
    *   Under **Branch**, click the dropdown, select `main`, and change the folder dropdown from `/ (root)` to `/docs`.
    *   Click **Save**.

4.  **Verify Deployment**  
    GitHub will run a deployment action. In 1–2 minutes, your viewer will be live at:
    `https://happy-kumar-sharma.github.io/error/viewer.html`
