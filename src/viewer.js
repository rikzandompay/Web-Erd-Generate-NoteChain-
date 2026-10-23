// frontend/src/viewer.js
// draw.io's own viewer, loaded once and shared by the preview and the image export.

const VIEWER_SRC = 'https://viewer.diagrams.net/js/viewer-static.min.js';
let viewerPromise = null;

export function loadViewer() {
  if (window.GraphViewer) return Promise.resolve();
  if (!viewerPromise) {
    viewerPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = VIEWER_SRC;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        viewerPromise = null;
        reject(new Error('draw.io viewer could not be loaded'));
      };
      document.body.appendChild(script);
    });
  }
  return viewerPromise;
}
