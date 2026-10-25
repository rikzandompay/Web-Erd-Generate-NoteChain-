// frontend/src/drawio.js
// Helpers shared by both modes for handling a generated .drawio file.

/** Page (tab) names inside a .drawio file. */
export function pageNames(xml) {
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  return [...doc.querySelectorAll('diagram')].map((d) => d.getAttribute('name') || 'Halaman');
}

/**
 * A file name that is different every time: "kasir-kopi_paket-diagram.drawio" becomes
 * "kasir-kopi_paket-diagram_20261025-143005.drawio", so a second download never turns into "(1)".
 */
export function uniqueFileName(fileName, now = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const safe = fileName.replace(/[\\/:*?"<>|]/g, '-');
  const dot = safe.lastIndexOf('.');
  return dot > 0 ? `${safe.slice(0, dot)}_${stamp}${safe.slice(dot)}` : `${safe}_${stamp}`;
}

/** Save the file through the browser's download; returns the name it was saved under. */
export function downloadFile(content, fileName, type = 'application/xml') {
  const name = uniqueFileName(fileName);
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return name;
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
