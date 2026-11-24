# Vendored JavaScript

Pinned copies, served from our own origin (no CDN; keeps the CSP simple).
Each file was extracted from the official npm tarball after verifying the
registry's `dist.integrity` (sha512) hash.

| File | Package | Version | Source file in tarball |
|---|---|---|---|
| `htmx-2.0.11.min.js` | `htmx.org` | 2.0.11 | `dist/htmx.min.js` |
| `alpine-3.17.5.min.js` | `alpinejs` | 3.17.5 | `dist/cdn.min.js` |

To upgrade: download the new version the same way, keep the version in the
filename, update `templates/base.html` and this table.
