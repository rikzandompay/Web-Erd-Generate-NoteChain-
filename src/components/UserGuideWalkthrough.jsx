import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X } from 'lucide-react';

const STEPS = [
  {
    id: 'welcome',
    title: 'Selamat datang',
    body: 'ERD Generator mengubah file SQL atau teks UML menjadi file draw.io yang langsung rapi. Panduan ini menjelaskan langkah-langkahnya.',
    target: null,
  },
  {
    id: 'pick-source',
    title: 'Pilih sumber diagram',
    body: 'Mulai dari tab "File SQL" kalau sudah punya file database, atau "Teks UML" untuk menulis diagram sendiri secara manual.',
    target: '[role="tablist"]',
  },
  {
    id: 'sql-mode',
    title: 'Mode File SQL',
    body: 'Seret file .sql ke area ini, atau klik untuk memilih. File harus berisi CREATE TABLE. Hasilnya dua halaman: ERD notasi Chen dan Class Diagram.',
    target: '#mode-panel',
    triggerMode: 'sql',
  },
  {
    id: 'uml-mode',
    title: 'Mode Teks UML',
    body: 'Tulis teks diagram langsung di editor. Pilih jenis diagram (Sequence, Activity, Class) lalu tulis teksnya. Awali dengan "===" untuk halaman baru.',
    target: '#mode-panel',
    triggerMode: 'uml',
  },
  {
    id: 'generate',
    title: 'Buat diagram',
    body: 'Tekan tombol "Buat diagram" untuk memproses. Kalau ada baris yang salah, pesannya muncul di panel Hasil dan bisa diklik untuk langsung ke baris itu.',
    target: 'button[class*="bg-accent"]',
  },
  {
    id: 'results',
    title: 'Lihat hasil',
    body: 'Preview diagram muncul di panel Hasil. Unduh sebagai file .drawio, atau buka langsung di app.diagrams.net untuk mengedit.',
    target: null,
  },
  {
    id: 'fixer',
    title: 'Perbaikan otomatis',
    body: 'Kalau ada error, panel "Perbaikan otomatis tersedia" muncul. Klik untuk memperbaiki baris yang bermasalah secara otomatis. Lihat perubahannya sebelum diterapkan.',
    target: null,
  },
  {
    id: 'theme',
    title: 'Tema terang dan gelap',
    body: 'Gunakan tombol di pojok kanan atas untuk beralih antara tema terang dan gelap. Defaultnya mengikuti setelan perangkat.',
    target: 'button[aria-label]',
  },
  {
    id: 'done',
    title: 'Siap pakai',
    body: 'Semua file dan teks diproses langsung, tidak disimpan di server. Buka tab "Panduan" kapan saja untuk referensi lengkap.',
    target: null,
  },
];

function Spotlight({ rect }) {
  if (!rect) return null;
  const pad = 8;
  const r = 10;
  return (
    <svg
      className="fixed inset-0 z-[998] pointer-events-none"
      width="100vw"
      height="100vh"
      style={{ width: '100vw', height: '100vh' }}
    >
      <defs>
        <mask id="spotlight-mask">
          <rect width="100%" height="100%" fill="white" />
          <rect
            x={rect.left - pad}
            y={rect.top - pad}
            width={rect.width + pad * 2}
            height={rect.height + pad * 2}
            rx={r}
            ry={r}
            fill="black"
          />
        </mask>
      </defs>
      <rect
        width="100%"
        height="100%"
        fill="rgba(0,0,0,0.45)"
        mask="url(#spotlight-mask)"
      />
    </svg>
  );
}

export default function UserGuideWalkthrough({ onClose, onSwitchMode }) {
  const [step, setStep] = useState(0);
  const [targetRect, setTargetRect] = useState(null);
  const dialogRef = useRef(null);
  const current = STEPS[step];

  const measureTarget = useCallback(() => {
    if (!current.target) {
      setTargetRect(null);
      return;
    }
    const el = document.querySelector(current.target);
    if (el) {
      const r = el.getBoundingClientRect();
      setTargetRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    } else {
      setTargetRect(null);
    }
  }, [current.target]);

  useEffect(() => {
    if (current.triggerMode && onSwitchMode) {
      onSwitchMode(current.triggerMode);
    }
    const timer = setTimeout(measureTarget, 120);
    return () => clearTimeout(timer);
  }, [step, current.triggerMode, onSwitchMode, measureTarget]);

  useEffect(() => {
    window.addEventListener('resize', measureTarget);
    window.addEventListener('scroll', measureTarget, true);
    return () => {
      window.removeEventListener('resize', measureTarget);
      window.removeEventListener('scroll', measureTarget, true);
    };
  }, [measureTarget]);

  useEffect(() => {
    const handleEsc = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  useEffect(() => {
    dialogRef.current?.focus();
  }, [step]);

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const prev = () => setStep((s) => Math.max(s - 1, 0));
  const isLast = step === STEPS.length - 1;
  const isFirst = step === 0;

  const dialogStyle = {};
  if (targetRect) {
    const belowSpace = window.innerHeight - targetRect.top - targetRect.height;
    if (belowSpace > 220) {
      dialogStyle.position = 'fixed';
      dialogStyle.top = `${targetRect.top + targetRect.height + 16}px`;
      dialogStyle.left = `${Math.max(16, Math.min(targetRect.left, window.innerWidth - 380))}px`;
    } else {
      dialogStyle.position = 'fixed';
      dialogStyle.top = `${Math.max(16, targetRect.top - 200)}px`;
      dialogStyle.left = `${Math.max(16, Math.min(targetRect.left, window.innerWidth - 380))}px`;
    }
  } else {
    dialogStyle.position = 'fixed';
    dialogStyle.top = '50%';
    dialogStyle.left = '50%';
    dialogStyle.transform = 'translate(-50%, -50%)';
  }

  return (
    <>
      <Spotlight rect={targetRect} />
      <div
        ref={dialogRef}
        role="dialog"
        aria-label={`Panduan langkah ${step + 1} dari ${STEPS.length}`}
        tabIndex={-1}
        className="z-[999] w-[min(360px,calc(100vw-32px))] rounded-xl border border-line bg-panel shadow-xl p-5 space-y-3"
        style={dialogStyle}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-medium text-muted">{step + 1} / {STEPS.length}</p>
            <h3 className="text-base font-semibold mt-0.5">{current.title}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Tutup panduan"
            className="shrink-0 w-9 h-9 flex items-center justify-center rounded-md hover:bg-desk transition-colors"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <p className="text-sm leading-relaxed text-muted">{current.body}</p>

        <div className="flex items-center gap-3 pt-1">
          <div className="flex gap-1.5">
            {STEPS.map((_, i) => (
              <span
                key={i}
                className={`block w-2 h-2 rounded-full transition-colors ${i === step ? 'bg-accent' : 'bg-line'}`}
                aria-hidden="true"
              />
            ))}
          </div>
          <div className="ml-auto flex gap-2">
            {!isFirst && (
              <button
                type="button"
                onClick={prev}
                className="min-h-[40px] px-4 text-sm font-medium rounded-md border border-edge hover:bg-desk transition-colors"
              >
                Kembali
              </button>
            )}
            {isLast ? (
              <button
                type="button"
                onClick={onClose}
                className="min-h-[40px] px-4 rounded-md bg-accent text-on-accent text-sm font-semibold hover:bg-accent-hover transition-colors"
              >
                Selesai
              </button>
            ) : (
              <button
                type="button"
                onClick={next}
                className="min-h-[40px] px-4 rounded-md bg-accent text-on-accent text-sm font-semibold hover:bg-accent-hover transition-colors"
              >
                {isFirst ? 'Mulai' : 'Lanjut'}
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
