// frontend/src/exportImage.js
// Export one page of a .drawio file as SVG or PNG, in the browser.
//
// The picture comes from draw.io's own viewer, rendered once at its real size
// (not the shrunken preview). Its labels are HTML inside <foreignObject>, which
// browsers refuse to turn into a PNG ("tainted canvas"), so each label's plain
// <text> fallback, which draw.io writes next to it, is used instead.

import { loadViewer } from './viewer';

const RENDER_WAIT_MS = 1200;

/** Build the SVG of one page: { svg, width, height } at 1x, with a white background. */
export async function renderPageSvg(xml, page) {
  await loadViewer();
  // A very wide hidden box keeps the diagram at scale 1 instead of fitting it to a column
  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;left:-200000px;top:0;width:100000px;';
  const element = document.createElement('div');
  element.className = 'mxgraph';
  element.setAttribute('data-mxgraph', JSON.stringify({ xml, page, toolbar: '', nav: false, resize: false }));
  host.appendChild(element);
  document.body.appendChild(host);
  try {
    const viewer = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Viewer draw.io tidak merespons.')), 15000);
      window.GraphViewer.createViewerForElement(element, (v) => {
        clearTimeout(timer);
        resolve(v);
      });
    });
    await new Promise((resolve) => setTimeout(resolve, RENDER_WAIT_MS));
    if (!viewer.graph?.getSvg) throw new Error('Viewer draw.io ini tidak mendukung ekspor gambar.');

    const root = viewer.graph.getSvg('#ffffff', 1, 10, false, null, true, null, null, null, false);
    root.querySelectorAll('foreignObject').forEach((fo) => {
      const holder = fo.parentElement;
      fo.remove();
      if (holder.tagName.toLowerCase() === 'switch') holder.replaceWith(...holder.childNodes);
    });
    root.querySelectorAll('a').forEach((a) => {
      if (/does not support/i.test(a.textContent)) a.remove();
    });
    const width = Math.ceil(parseFloat(root.getAttribute('width')));
    const height = Math.ceil(parseFloat(root.getAttribute('height')));
    return { svg: new XMLSerializer().serializeToString(root), width, height };
  } finally {
    host.remove();
  }
}

function save(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName.replace(/[\\/:*?"<>|]/g, '-');
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function downloadSvg(xml, page, baseName) {
  const { svg } = await renderPageSvg(xml, page);
  save(new Blob([`<?xml version="1.0" encoding="UTF-8"?>\n${svg}`], { type: 'image/svg+xml' }), `${baseName}.svg`);
}

/** PNG at `scale` times the diagram's size (2 or 3 is sharp enough for a printed report). */
export async function downloadPng(xml, page, baseName, scale) {
  const { svg, width, height } = await renderPageSvg(xml, page);
  const image = new Image();
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }));
  try {
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = () => reject(new Error('Gambar diagram tidak bisa dibaca browser.'));
      image.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
  const canvas = document.createElement('canvas');
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.scale(scale, scale);
  ctx.drawImage(image, 0, 0, width, height);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('PNG terlalu besar untuk dibuat browser. Coba skala lebih kecil atau unduh SVG.');
  save(blob, `${baseName}-${scale}x.png`);
}
