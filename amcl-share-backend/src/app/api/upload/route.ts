import { put } from '@vercel/blob';
import { NextResponse } from 'next/server';

function generateRandomId(length = 8) {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let i = 0; i < length; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}

export async function POST(request: Request) {
    try {
        const authHeader = request.headers.get('authorization');
        const secret = process.env.AMCL_SHARE_SECRET;

        // Only enforce auth if the environment variable is set.
        // Recommended to set this in Vercel to prevent abuse.
        if (secret && authHeader !== `Bearer ${secret}`) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
        }

        const formData = await request.formData();
        const file = formData.get('file');

        if (!file || !(file instanceof File)) {
            return NextResponse.json({ error: 'No file provided' }, { status: 400 });
        }

        const id = generateRandomId();
        const filename = `amcl-shares/${id}.html`;

        // Upload to Vercel Blob
        const blob = await put(filename, file, {
            access: 'public',
            contentType: 'text/html',
        });

        // The public URL on our domain, not the Vercel Blob URL directly
        // This allows us to proxy it and strip the CSP headers
        const jpdzUrl = new URL(`/c/${id}`, request.url).toString();

        // The CLI expects plain text URL or JSON with `url`
        return NextResponse.json({ url: jpdzUrl });
    } catch (err: any) {
        console.error('Upload error:', err);
        return NextResponse.json({ error: 'Upload failed', details: err.message }, { status: 500 });
    }
}
