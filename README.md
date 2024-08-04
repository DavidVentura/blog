This repo hosts the scripts used to generate [my blog](https://blog.davidv.dev/).

* Posts are written in Markdown at `blog/posts/`
* Each post may have its own assets at `blog/posts/<post>/assets/`
    * These assets are transformed, if necessary. SVGs get custom CSS injected to support dark mode.
* The `generate.py` command generates:
    * All HTML posts
    * The index
    * The index per tag
    * The RSS feed
* The `webring-generator.py` generates `blogs-i-follow.html` from an OPML file.

Requires:
- python + pip (`requirements.txt` file)
- pnpm (tailwind, mermaid svg generation)

The produced HTML + CSS is rsynced to a VPS running Caddy. The config is at `Caddyfile`.
