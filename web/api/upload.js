// Issues a short-lived token so the browser can upload straight to Blob storage.
// Videos are far larger than the 4.5 MB a function body allows, so they must not
// pass through the function at all.
import { handleUpload } from '@vercel/blob/client';

const MAX_BYTES = 300 * 1024 * 1024;

export async function POST(request) {
  const body = await request.json();
  try {
    const json = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async () => ({
        allowedContentTypes: ['video/mp4', 'video/quicktime', 'video/x-m4v', 'video/webm'],
        maximumSizeInBytes: MAX_BYTES,
        addRandomSuffix: true,
        // Uploads are deleted after an hour: this is a measuring tool, not a
        // place to store anyone's data.
        cacheControlMaxAge: 3600,
      }),
      onUploadCompleted: async () => {},
    });
    return Response.json(json);
  } catch (err) {
    console.error('upload token failed', err);
    return Response.json({ error: err.message }, { status: 400 });
  }
}
