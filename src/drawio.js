// frontend/src/drawio.js
// Helpers shared by both modes for handling a generated .drawio file.

/** Page (tab) names inside a .drawio file. */
export function pageNames(xml) {
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  return [...doc.querySelectorAll('diagram')].map((d) => d.getAttribute('name') || 'Halaman');
}

/** Save the file through the browser's download. */
export function downloadFile(xml, fileName, type = 'application/xml') {
  const url = URL.createObjectURL(new Blob([xml], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName.replace(/[\\/:*?"<>|]/g, '-');
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * Link that opens the file in app.diagrams.net, packed like draw.io's own
 * #R links (URI-encode, raw-deflate, base64), the same as api/uml.py does.
 */
export async function drawioUrl(xml) {
  const encoded = new TextEncoder().encode(encodeURIComponent(xml));
  const stream = new Blob([encoded]).stream().pipeThrough(new CompressionStream('deflate-raw'));
  const bytes = new Uint8Array(await new Response(stream).arrayBuffer());
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return `https://app.diagrams.net/#R${encodeURIComponent(btoa(binary))}`;
}

/** Readable message for a failed API call. */
export function apiErrorMessage(err) {
  if (!err.response) {
    return 'Tidak bisa menghubungi server. Pastikan backend berjalan, lalu coba lagi.';
  }
  let data = err.response.data;
  if (typeof data === 'string') {
    try {
      data = JSON.parse(data);
    } catch {
      data = null;
    }
  }
  return data?.detail || `Server membalas dengan kode ${err.response.status}. Coba lagi.`;
}
