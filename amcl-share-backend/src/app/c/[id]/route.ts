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

        // Return it with full styling enabled (No CSP blocking)
        return new NextResponse(html, {
            headers: {
                'Content-Type': 'text/html; charset=utf-8',
                'Cache-Control': 'public, max-age=31536000, immutable',
                // Critical: explicit lack of content-security-policy
            }
        });
    } catch (err) {
        console.error('Fetch error:', err);
        return new NextResponse('Server Error', { status: 500 });
    }
}
