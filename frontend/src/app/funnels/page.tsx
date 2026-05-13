'use client';

import { useState, useEffect, useCallback } from 'react';
import useSWR from 'swr';
import {
  DndContext, closestCenter, KeyboardSensor, PointerSensor,
  useSensor, useSensors, DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove, SortableContext, sortableKeyboardCoordinates,
  useSortable, verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import AppShell from '@/components/layout/AppShell';
import FunnelChart from '@/components/charts/FunnelChart';
import {
  listFunnels, createFunnel, updateFunnel, deleteFunnel,
  getFunnelData, listFunnelEvents,
  type Funnel, type FunnelData,
} from '@/lib/api';

// ── Sortable step item ────────────────────────────────────────────────────────

function SortableStep({
  id, value, onChange, onRemove, suggestions,
}: {
  id: string; value: string;
  onChange: (v: string) => void;
  onRemove: () => void;
  suggestions: string[];
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} className="flex items-center gap-2">
      {/* Drag handle */}
      <button
        {...attributes}
        {...listeners}
        className="text-gray-300 hover:text-gray-500 cursor-grab active:cursor-grabbing p-1"
        type="button"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 8h16M4 16h16" />
        </svg>
      </button>

      {/* Autocomplete input */}
      <div className="flex-1 relative">
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          list={`suggestions-${id}`}
          placeholder="Event name…"
          className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2
                     focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <datalist id={`suggestions-${id}`}>
          {suggestions.map(s => <option key={s} value={s} />)}
        </datalist>
      </div>

      <button
        type="button"
        onClick={onRemove}
        className="text-gray-300 hover:text-red-400 transition-colors p-1"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

// ── Funnel builder panel ──────────────────────────────────────────────────────

interface BuilderProps {
  funnel: Funnel | null;           // null = new funnel
  eventSuggestions: string[];
  onSaved: (f: Funnel) => void;
  onCancel: () => void;
}

function FunnelBuilder({ funnel, eventSuggestions, onSaved, onCancel }: BuilderProps) {
  const [name,   setName]   = useState(funnel?.name ?? '');
  const [steps,  setSteps]  = useState<{ id: string; value: string }[]>(
    funnel?.steps.length
      ? funnel.steps.map((s, i) => ({ id: `step-${i}-${Date.now()}`, value: s }))
      : [{ id: 'step-0', value: '' }, { id: 'step-1', value: '' }],
  );
  const [saving,  setSaving]  = useState(false);
  const [error,   setError]   = useState('');

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      setSteps(prev => {
        const oldIndex = prev.findIndex(s => s.id === active.id);
        const newIndex = prev.findIndex(s => s.id === over.id);
        return arrayMove(prev, oldIndex, newIndex);
      });
    }
  }

  function addStep() {
    setSteps(prev => [...prev, { id: `step-${Date.now()}`, value: '' }]);
  }

  function removeStep(id: string) {
    if (steps.length <= 2) return;
    setSteps(prev => prev.filter(s => s.id !== id));
  }

  function updateStep(id: string, value: string) {
    setSteps(prev => prev.map(s => s.id === id ? { ...s, value } : s));
  }

  async function handleSave() {
    const stepValues = steps.map(s => s.value.trim()).filter(Boolean);
    if (!name.trim())        { setError('Give the funnel a name'); return; }
    if (stepValues.length < 2) { setError('Add at least 2 steps'); return; }
    setSaving(true); setError('');
    try {
      const saved = funnel
        ? await updateFunnel(funnel.id, { name: name.trim(), steps: stepValues })
        : await createFunnel(name.trim(), stepValues);
      onSaved(saved);
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card space-y-4">
      <h3 className="text-sm font-semibold text-gray-900">
        {funnel ? 'Edit funnel' : 'New funnel'}
      </h3>

      <input
        type="text"
        value={name}
        onChange={e => setName(e.target.value)}
        placeholder="Funnel name"
        className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2
                   focus:outline-none focus:ring-2 focus:ring-indigo-400"
        maxLength={120}
      />

      <div className="space-y-2">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          Steps — drag to reorder
        </p>
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext items={steps.map(s => s.id)} strategy={verticalListSortingStrategy}>
            {steps.map(step => (
              <SortableStep
                key={step.id}
                id={step.id}
                value={step.value}
                onChange={v => updateStep(step.id, v)}
                onRemove={() => removeStep(step.id)}
                suggestions={eventSuggestions}
              />
            ))}
          </SortableContext>
        </DndContext>

        {steps.length < 10 && (
          <button
            type="button"
            onClick={addStep}
            className="text-xs text-indigo-600 hover:text-indigo-800 font-medium
                       flex items-center gap-1"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            Add step
          </button>
        )}
      </div>

      {error && (
        <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
      )}

      <div className="flex gap-2 pt-1">
        <button
          onClick={handleSave} disabled={saving}
          className="flex-1 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60
                     text-white text-sm font-medium rounded-lg py-2 transition-colors"
        >
          {saving ? 'Saving…' : 'Save funnel'}
        </button>
        <button
          onClick={onCancel}
          className="px-4 text-sm text-gray-600 border border-gray-200 rounded-lg
                     hover:bg-gray-50 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── Funnel results panel ──────────────────────────────────────────────────────

function FunnelResults({ funnel, days }: { funnel: Funnel; days: number }) {
  const { data, isLoading } = useSWR(
    ['funnel-data', funnel.id, days],
    () => getFunnelData(funnel.id, days),
    { refreshInterval: 300_000 },
  );

  if (isLoading) return <div className="h-40 bg-gray-100 rounded animate-pulse" />;
  if (!data || data.steps.length === 0) {
    return (
      <div className="h-40 flex items-center justify-center text-sm text-gray-400">
        No events in the last {days} days
      </div>
    );
  }

  return <FunnelChart data={data.steps} />;
}

// ── Page ──────────────────────────────────────────────────────────────────────

const DAYS_OPTIONS = [7, 14, 30, 90];

export default function FunnelsPage() {
  const [days,        setDays]        = useState(30);
  const [selected,    setSelected]    = useState<Funnel | null>(null);
  const [editing,     setEditing]     = useState<Funnel | 'new' | null>(null);
  const [funnels,     setFunnels]     = useState<Funnel[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);

  useSWR('funnels', listFunnels, { onSuccess: setFunnels });
  useSWR('funnel-events', listFunnelEvents, {
    onSuccess: setSuggestions,
    revalidateOnFocus: false,
  });

  // Auto-select first funnel
  useEffect(() => {
    if (funnels.length > 0 && !selected) setSelected(funnels[0]);
  }, [funnels, selected]);

  async function handleDelete(f: Funnel) {
    if (!confirm(`Delete "${f.name}"?`)) return;
    await deleteFunnel(f.id);
    setFunnels(prev => prev.filter(x => x.id !== f.id));
    if (selected?.id === f.id) setSelected(null);
  }

  function handleSaved(saved: Funnel) {
    setFunnels(prev => {
      const exists = prev.find(f => f.id === saved.id);
      return exists ? prev.map(f => f.id === saved.id ? saved : f) : [saved, ...prev];
    });
    setSelected(saved);
    setEditing(null);
  }

  return (
    <AppShell>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Custom Funnels</h1>
          <p className="text-sm text-gray-500 mt-0.5">Build and track multi-step user journeys</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            className="input w-auto text-sm py-1.5"
          >
            {DAYS_OPTIONS.map(d => <option key={d} value={d}>Last {d} days</option>)}
          </select>
          <button
            onClick={() => setEditing('new')}
            className="btn-primary text-sm px-4 py-1.5 flex items-center gap-1.5"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            New funnel
          </button>
        </div>
      </div>

      <div className="grid grid-cols-[280px_1fr] gap-6">
        {/* Sidebar: list of funnels */}
        <div className="space-y-2">
          {funnels.length === 0 && editing !== 'new' && (
            <div className="card text-center py-8">
              <p className="text-sm text-gray-400">No funnels yet</p>
              <button
                onClick={() => setEditing('new')}
                className="text-xs text-indigo-600 hover:underline mt-2"
              >
                Create your first funnel
              </button>
            </div>
          )}
          {funnels.map(f => (
            <div
              key={f.id}
              onClick={() => { setSelected(f); setEditing(null); }}
              className={`card cursor-pointer transition-all group ${
                selected?.id === f.id
                  ? 'ring-2 ring-indigo-500 ring-offset-1'
                  : 'hover:border-gray-300'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-gray-900 truncate">{f.name}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{f.steps.length} steps</p>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {f.steps.slice(0, 3).map((s, i) => (
                      <span key={i} className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                        {s.length > 14 ? s.slice(0, 14) + '…' : s}
                      </span>
                    ))}
                    {f.steps.length > 3 && (
                      <span className="text-xs text-gray-400">+{f.steps.length - 3} more</span>
                    )}
                  </div>
                </div>
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-2">
                  <button
                    onClick={e => { e.stopPropagation(); setEditing(f); }}
                    className="p-1 text-gray-400 hover:text-indigo-600"
                    title="Edit"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round"
                        d="M15.232 5.232l3.536 3.536M9 11l6-6 3 3-6 6H9v-3z" />
                    </svg>
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); handleDelete(f); }}
                    className="p-1 text-gray-400 hover:text-red-500"
                    title="Delete"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round"
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Main: builder or results */}
        <div>
          {editing ? (
            <FunnelBuilder
              funnel={editing === 'new' ? null : editing}
              eventSuggestions={suggestions}
              onSaved={handleSaved}
              onCancel={() => setEditing(null)}
            />
          ) : selected ? (
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-gray-900">{selected.name}</h2>
                <button
                  onClick={() => setEditing(selected)}
                  className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                >
                  Edit
                </button>
              </div>
              <FunnelResults funnel={selected} days={days} />
            </div>
          ) : (
            <div className="card flex items-center justify-center h-48 text-sm text-gray-400">
              Select a funnel to view results
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
