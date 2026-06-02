import { list } from '@vercel/blob';
import { NextResponse } from 'next/server';

export async function GET(
    request: Request,
    { params }: { params: Promise<{ id: string }> }
) {
    try {
        const { id } = await params;

        // Sanitize ID to prevent directory traversal
        if (!/^[a-zA-Z0-9]+$/.test(id)) {
            return new NextResponse('Invalid ID', { status: 400 });
        }

        const prefix = `amcl-shares/${id}.html`;

        // Find the blob in Vercel Storage
        const { blobs } = await list({ prefix });

        if (blobs.length === 0) {
            return new NextResponse(
                `<html><body style="font-family: system-ui; text-align: center; margin-top: 50px;">
          <h1>404 - Chat Not Found</h1>
          <p>This conversation either expired or does not exist.</p>
         </body></html>`,
                { status: 404, headers: { 'Content-Type': 'text/html' } }
            );
        }

        // Fetch the raw HTML from the blob
        const response = await fetch(blobs[0].url);
        if (!response.ok) {
            throw new Error(`Failed to fetch blob: ${response.statusText}`);
        }
        const html = await response.text();

        // Serve the self-generated HTML with a hardened CSP tuned to its
        // needs: inline styles, inline <style>, one inline <script> + inline
        // onclick handlers, and Google Fonts. Defense-in-depth; auth on the
        // upload routes is the primary control.
        return new NextResponse(html, {
            headers: {
                'Content-Type': 'text/html; charset=utf-8',
                'Cache-Control': 'public, max-age=31536000, immutable',
                'Content-Security-Policy':
                    "default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; script-src 'unsafe-inline'; img-src data: https:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
                'X-Content-Type-Options': 'nosniff',
                'X-Frame-Options': 'DENY',
            }
        });
    } catch (err) {
        console.error('Fetch error:', err);
        return new NextResponse('Server Error', { status: 500 });
    }
}
