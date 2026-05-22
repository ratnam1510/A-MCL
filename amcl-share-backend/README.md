# amcl-share-backend

The Next.js app that powers shared A/MCL project snapshots
(<https://amcl.dev/c/...> links). It exposes a tiny upload endpoint that
stores the HTML payload in Vercel Blob storage and a redirect route that
serves it back to anyone with the link.

This package is published with the rest of the [A/MCL repo](../README.md)
under the MIT license. It is optional — the core `amcl-server` works
without it. You only need to run this app if you want to host your own
share backend instead of using the default one.

## Routes

- `POST /api/upload` — Accepts a multipart form upload of the rendered
  share HTML and returns the public URL.
- `GET  /c/[id]` — Redirects to the stored HTML for a given share id.

## Running locally

```bash
npm install
cp .env.local.example .env.local   # fill in your own Vercel Blob token
npm run dev
```

Open <http://localhost:3000>.

## Deploying

The project is set up for Vercel. Push to the connected git remote and
Vercel will build and deploy automatically. The only required
environment variable is `BLOB_READ_WRITE_TOKEN` for Vercel Blob storage.
