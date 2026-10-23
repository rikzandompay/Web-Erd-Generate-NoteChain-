// frontend/src/components/DiagramPreview.jsx
import React, { useEffect, useRef, useState } from 'react';
import { loadViewer } from '../viewer';

// One page of the file, drawn on a sheet of paper. The sheet stays light in
// both themes because that is how the file looks in draw.io itself.
export default function DiagramPreview({ xml, page, pageName }) {
  const containerRef = useRef(null);
  const [shown, setShown] = useState({ xml: null, page: null, status: 'loading' });
  const status = shown.xml === xml && shown.page === page ? shown.status : 'loading';

  useEffect(() => {
    let cancelled = false;
    loadViewer()
      .then(() => {
        if (cancelled || !containerRef.current) return;
        const element = document.createElement('div');
        element.className = 'mxgraph';
        element.setAttribute('data-mxgraph', JSON.stringify({
          xml, page, toolbar: 'zoom', 'toolbar-nohide': true, nav: false, resize: true, lightbox: false,
        }));
        containerRef.current.replaceChildren(element);
        window.GraphViewer.createViewerForElement(element);
        setShown({ xml, page, status: 'ready' });
      })
      .catch(() => {
        if (!cancelled) setShown({ xml, page, status: 'failed' });
      });
    return () => {
      cancelled = true;
    };
  }, [xml, page]);

  if (status === 'failed') {
    return (
      <p className="rounded-md border border-line p-4 text-sm text-muted">
        Preview butuh koneksi internet untuk memuat viewer draw.io. File tetap bisa diunduh atau dibuka di draw.io.
      </p>
    );
  }

  return (
    <figure className="m-0">
      <div className="rounded-md bg-paper p-3 overflow-auto shadow-[0_1px_2px_rgb(0_0_0/0.08),0_4px_16px_rgb(0_0_0/0.06)]">
        {status === 'loading' && <p className="p-4 text-sm text-[#5C5951]">Memuat preview…</p>}
        <div ref={containerRef} />
      </div>
      <figcaption className="sr-only">Preview halaman {pageName}</figcaption>
    </figure>
  );
}
