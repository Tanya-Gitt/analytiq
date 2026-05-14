'use client';

/**
 * ConfirmDialog — shared confirmation modal in two modes:
 *
 * 1. type-to-confirm (confirmWord provided):
 *    User must type the exact word (e.g. "delete", "logout") before the
 *    action button enables.  Used for irreversible destructive actions.
 *
 * 2. simple (no confirmWord):
 *    Plain "Cancel / Confirm" dialog.  Used for moderate actions.
 *
 * Rendered via ReactDOM.createPortal directly onto document.body so it
 * escapes every CSS stacking context (sticky sidebars, Recharts SVG layers,
 * etc.).  z-[9999] then genuinely means "above everything".
 */

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface Props {
  open:          boolean;
  title:         string;
  description?:  string;
  /** If provided, enables type-to-confirm mode. User must type this exact word. */
  confirmWord?:  string;
  confirmLabel?: string;
  onConfirm:     () => void;
  onClose:       () => void;
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmWord,
  confirmLabel = 'Confirm',
  onConfirm,
  onClose,
}: Props) {
  const [typed,   setTyped]   = useState('');
  const [mounted, setMounted] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Track client-side mount so createPortal never runs on the server
  useEffect(() => { setMounted(true); }, []);

  // Reset typed value whenever the dialog opens
  useEffect(() => {
    if (open) {
      setTyped('');
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open || !mounted) return null;

  const typeMatch = confirmWord
    ? typed === confirmWord
    : true;

  function handleConfirm() {
    if (!typeMatch) return;
    onConfirm();
    onClose();
  }

  // Portal onto document.body — escapes sticky/transform stacking contexts
  return createPortal(
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6 space-y-4">

        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-red-500">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round"
                    d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                </svg>
              </span>
              <h2 className="text-base font-bold text-gray-900">{title}</h2>
            </div>
            {description && (
              <p className="text-sm text-gray-500 leading-relaxed">{description}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 flex-shrink-0 mt-0.5"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Type-to-confirm input */}
        {confirmWord && (
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-gray-600">
              Type{' '}
              <code className="bg-gray-100 text-red-600 px-1.5 py-0.5 rounded font-mono font-semibold">
                {confirmWord}
              </code>{' '}
              to confirm
            </label>
            <input
              ref={inputRef}
              type="text"
              value={typed}
              onChange={e => setTyped(e.target.value.replace(/\s/g, ''))}
              onKeyDown={e => e.key === 'Enter' && typeMatch && handleConfirm()}
              onPaste={e => e.preventDefault()}
              onDrop={e => e.preventDefault()}
              placeholder={confirmWord}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              className="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm font-mono
                         focus:outline-none focus:ring-2 focus:ring-red-400 focus:border-transparent
                         placeholder:text-gray-300"
            />
          </div>
        )}

        {/* Buttons */}
        <div className="flex gap-2 pt-1">
          <button
            onClick={onClose}
            className="flex-1 py-2 rounded-xl border border-gray-200 text-sm text-gray-600
                       hover:bg-gray-50 transition-colors font-medium"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={!typeMatch}
            className="flex-1 py-2 rounded-xl bg-red-600 text-white text-sm font-medium
                       hover:bg-red-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
