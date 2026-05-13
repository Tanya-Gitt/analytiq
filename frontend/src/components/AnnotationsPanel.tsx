'use client';

import { useState } from 'react';
import { createAnnotation, deleteAnnotation, type Annotation } from '@/lib/api';

const PRESET_COLORS = [
  '#6366f1', // indigo (default)
  '#ef4444', // red
  '#f59e0b', // amber
  '#10b981', // emerald
  '#3b82f6', // blue
  '#ec4899', // pink
  '#8b5cf6', // violet
];

interface Props {
  segment: 'A' | 'B';
  annotations: Annotation[];
  onAdd: (a: Annotation) => void;
  onDelete: (id: string) => void;
}

export default function AnnotationsPanel({ segment, annotations, onAdd, onDelete }: Props) {
  const [open, setOpen]     = useState(false);
  const [date, setDate]     = useState('');
  const [label, setLabel]   = useState('');
  const [color, setColor]   = useState('#6366f1');
  const [saving, setSaving] = useState(false);

  async function handleAdd() {
    if (!date || !label.trim()) return;
    setSaving(true);
    try {
      const ann = await createAnnotation({ segment, date, label: label.trim(), color });
      onAdd(ann);
      setDate('');
      setLabel('');
      setColor('#6366f1');
    } catch (e: unknown) {
      alert((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    await deleteAnnotation(id);
    onDelete(id);
  }

  return (
    <div className="mt-4">
      {/* Toggle button */}
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors"
      >
        <svg
          className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-90' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        Annotations
        {annotations.length > 0 && (
          <span className="bg-indigo-100 text-indigo-700 text-xs px-1.5 py-0.5 rounded-full font-normal">
            {annotations.length}
          </span>
        )}
      </button>

      {open && (
        <div className="mt-3 bg-gray-50 rounded-xl p-4 space-y-4">
          {/* Add form */}
          <div className="space-y-2">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
              Add annotation
            </p>
            <div className="flex gap-2">
              <input
                type="date"
                value={date}
                onChange={e => setDate(e.target.value)}
                className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
              <input
                type="text"
                placeholder="Label"
                value={label}
                onChange={e => setLabel(e.target.value)}
                maxLength={120}
                className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Color:</span>
              {PRESET_COLORS.map(c => (
                <button
                  key={c}
                  onClick={() => setColor(c)}
                  style={{ backgroundColor: c }}
                  className={`w-5 h-5 rounded-full transition-transform ${
                    color === c ? 'ring-2 ring-offset-1 ring-gray-400 scale-110' : 'hover:scale-110'
                  }`}
                />
              ))}
            </div>
            <button
              onClick={handleAdd}
              disabled={saving || !date || !label.trim()}
              className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-medium px-4 py-1.5 rounded-lg transition-colors"
            >
              {saving ? 'Adding…' : 'Add marker'}
            </button>
          </div>

          {/* List */}
          {annotations.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                Markers
              </p>
              <ul className="space-y-1.5">
                {annotations.map(ann => (
                  <li key={ann.id} className="flex items-center gap-2">
                    <span
                      className="w-3 h-3 rounded-full shrink-0"
                      style={{ backgroundColor: ann.color }}
                    />
                    <span className="text-xs text-gray-500 font-mono">{ann.date}</span>
                    <span className="text-xs text-gray-700 flex-1 truncate">{ann.label}</span>
                    <button
                      onClick={() => handleDelete(ann.id)}
                      className="text-xs text-red-400 hover:text-red-600"
                      title="Remove"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
