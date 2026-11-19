# Publishing as a static site

A static export writes the whole resident site, in English and Spanish, as plain
files: one page per service line and per street, the map data, and a search index
that the browser searches by itself. Upload the folder to any free static host and
there is no server to run or patch.

## Export

From the staff area: **Overview → Download static site** gives you a `.zip`.

From the command line:

```bash
pipetrace export_static site/                         # site lives at the domain root
pipetrace export_static site/ --base-url /leadlines/  # site lives under a path
pipetrace export_static site/ --zip site.zip          # also write a zip
```

Re-export and re-upload whenever you import a new inventory.

## Where to host it

* **GitHub Pages**: push the folder to a repository and enable Pages. For a project
  site at `https://<user>.github.io/<repo>/`, export with `--base-url /<repo>/`. The
  export includes `.nojekyll` and a `404.html`.
* **Netlify, Cloudflare Pages**: drag and drop the folder.
* **Your town's web server**: copy the folder into a directory and pass that path as
  `--base-url`.

## Forms on a static site

A static site can't store inspection requests or photos itself. Choose one:

1. **Send them to a Pipetrace server** (best): set *Site settings → Form endpoint for
   the static site* to `https://your-pipetrace-server/api/submit/` before exporting.
   Submissions arrive in that server's staff area. Limit which sites may post with
   `PIPETRACE_STATIC_SITE_ORIGINS`.
2. **Email** (no server at all): leave the endpoint blank and set the utility email.
   The forms open the resident's email app with everything filled in; for photos they
   attach the picture themselves.

## What works without a server

Everything residents read: address search with suggestions, every result page, the
map, the coin-and-magnet guide, filter advice, questions and the street index. Search
needs JavaScript; the street index works without it.
