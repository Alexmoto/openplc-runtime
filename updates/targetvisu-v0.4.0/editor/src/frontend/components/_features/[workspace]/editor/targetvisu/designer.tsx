// SPDX-License-Identifier: GPL-3.0-only
import { useEffect, useMemo, useRef, useState } from 'react'
import { v4 as uuid } from 'uuid'

import type {
  TargetVisuDocument,
  VisuElement,
  VisuScreen,
  VisuSymbol,
  VisuValue,
} from '../../../../../../middleware/shared/targetvisu/model'
import {
  exportVisualization,
  fitElement,
  isNumericType,
  newElement,
  newScreen,
  TargetVisuSchema,
  validateBindings,
} from '../../../../../../middleware/shared/targetvisu/model'

const KINDS: VisuElement['kind'][] = ['rectangle', 'ellipse', 'line', 'text', 'indicator', 'button', 'number']
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T
const control =
  'rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-800 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100'
const button = `${control} hover:border-blue-500`
const valueAt = (values: Record<string, VisuValue>, path: string) =>
  values[Object.keys(values).find((p) => p.toLowerCase() === path.toLowerCase()) ?? path]

function NumericField({
  label,
  value,
  change,
  min,
  max,
  step,
}: {
  label: string
  value: number
  change: (n: number) => void
  min: number
  max: number
  step: number
}) {
  const [draft, setDraft] = useState(String(value))
  useEffect(() => setDraft(String(value)), [value])
  const commit = () => {
    const number = draft.trim() === '' ? value : Number(draft)
    const next = Number.isFinite(number)
      ? Math.max(min, Math.min(max, step === 1 ? Math.round(number) : number))
      : value
    setDraft(String(next))
    change(next)
  }
  return (
    <label className='flex items-center justify-between gap-2'>
      {label}
      <input
        className={`${control} w-24`}
        aria-label={label}
        type='number'
        min={min}
        max={max}
        step={step}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            commit()
          }
        }}
      />
    </label>
  )
}

function RenderElement({
  element: e,
  preview,
  values,
}: {
  element: VisuElement
  preview: boolean
  values: Record<string, VisuValue>
}) {
  const value = valueAt(values, e.bindings.value)
  const fill = e.kind === 'indicator' && preview && value === true ? e.activeFill : e.fill
  const label =
    e.kind === 'number'
      ? preview
        ? typeof value === 'number'
          ? value.toFixed(e.decimals)
          : '—'
        : (0).toFixed(e.decimals)
      : e.kind === 'text' && e.bindings.value
        ? preview
          ? String(value ?? '—')
          : `{${e.bindings.value}}`
        : e.text
  return (
    <>
      {e.kind === 'ellipse' || e.kind === 'indicator' ? (
        <ellipse
          cx={e.x + e.width / 2}
          cy={e.y + e.height / 2}
          rx={e.width / 2}
          ry={e.height / 2}
          fill={fill}
          stroke={e.stroke}
          strokeWidth={e.strokeWidth}
        />
      ) : e.kind === 'line' ? (
        <line
          x1={e.lineDirection === 'vertical' ? e.x + e.width / 2 : e.x}
          y1={
            e.lineDirection === 'horizontal'
              ? e.y + e.height / 2
              : e.lineDirection === 'diagonal-up'
                ? e.y + e.height
                : e.y
          }
          x2={e.lineDirection === 'vertical' ? e.x + e.width / 2 : e.x + e.width}
          y2={
            e.lineDirection === 'horizontal'
              ? e.y + e.height / 2
              : e.lineDirection === 'diagonal-up'
                ? e.y
                : e.y + e.height
          }
          stroke={e.stroke}
          strokeWidth={Math.max(1, e.strokeWidth)}
        />
      ) : e.kind !== 'text' ? (
        <rect
          x={e.x}
          y={e.y}
          width={e.width}
          height={e.height}
          rx={e.kind === 'button' ? 6 : 0}
          fill={fill}
          stroke={e.stroke}
          strokeWidth={e.strokeWidth}
        />
      ) : null}
      {label && (
        <svg x={e.x + 4} y={e.y} width={Math.max(1, e.width - 8)} height={e.height} overflow='hidden'>
          <text
            x='50%'
            y='50%'
            textAnchor='middle'
            dominantBaseline='central'
            fill={e.textColor}
            fontFamily='sans-serif'
            fontSize={e.fontSize}
            style={{ userSelect: 'none', pointerEvents: 'none' }}
          >
            {label}
          </text>
        </svg>
      )}
    </>
  )
}

export function TargetVisuDesigner({
  document: doc,
  symbols,
  onChange,
  readOnly = false,
}: {
  document: TargetVisuDocument
  symbols: VisuSymbol[]
  onChange: (document: TargetVisuDocument) => void
  readOnly?: boolean
}) {
  const [screenId, setScreenId] = useState(doc.startScreen)
  const [selection, setSelection] = useState<string[]>([])
  const [preview, setPreview] = useState(false)
  const [values, setValues] = useState<Record<string, VisuValue>>({})
  const [zoom, setZoom] = useState(1)
  const [snap, setSnap] = useState(true)
  const [error, setError] = useState('')
  const [undo, setUndo] = useState<TargetVisuDocument[]>([])
  const [redo, setRedo] = useState<TargetVisuDocument[]>([])
  const svg = useRef<SVGSVGElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const clipboard = useRef<VisuElement[]>([])
  const drag = useRef<{
    base: TargetVisuDocument
    screen: VisuScreen
    ids: string[]
    start: { x: number; y: number }
    resize: boolean
  } | null>(null)
  const screen = doc.screens.find((s) => s.id === screenId) ?? doc.screens[0]
  const current = screen?.elements.find((e) => e.id === selection[0])
  const errors = useMemo(() => validateBindings(doc, symbols), [doc, symbols])
  const blocked = readOnly || preview
  const momentaryTargets = JSON.stringify(
    doc.screens.flatMap((s) =>
      s.elements.filter((e) => e.action.kind === 'momentary' && e.action.target).map((e) => e.action.target),
    ),
  )
  useEffect(() => {
    setValues((previous) => {
      const next = { ...previous }
      for (const path of JSON.parse(momentaryTargets) as string[]) {
        const canonical = Object.keys(previous).find((key) => key.toLowerCase() === path.toLowerCase()) ?? path
        next[canonical] = false
      }
      return next
    })
  }, [preview, screen?.id, momentaryTargets])
  useEffect(() => {
    setSelection([])
  }, [screen?.id])
  useEffect(() => {
    setValues((previous) =>
      Object.fromEntries(
        symbols.map((s) => [s.path, previous[s.path] ?? (s.type === 'BOOL' ? false : isNumericType(s.type) ? 0 : '')]),
      ),
    )
  }, [symbols])
  const apply = (next: TargetVisuDocument, history = true) => {
    if (readOnly) return
    const result = TargetVisuSchema.safeParse(next)
    if (!result.success) {
      setError(result.error.issues[0]?.message ?? 'Invalid visualization')
      return
    }
    if (JSON.stringify(doc) === JSON.stringify(next)) return
    if (history) {
      setUndo((past) => [...past.slice(-99), clone(doc)])
      setRedo([])
    }
    setError('')
    onChange(result.data)
  }
  const editScreen = (update: (screen: VisuScreen) => VisuScreen) => {
    if (!screen || blocked) return
    apply({ ...doc, screens: doc.screens.map((s) => (s.id === screen.id ? update(s) : s)) })
  }
  const patchElement = (patch: Partial<VisuElement>) =>
    editScreen((s) => ({
      ...s,
      elements: s.elements.map((e) => (selection.includes(e.id) ? fitElement({ ...e, ...patch }, s) : e)),
    }))
  const addScreen = () => {
    let index = doc.screens.length + 1
    while (doc.screens.some((s) => s.name.toLowerCase() === `screen${index}`)) index++
    const next = newScreen(uuid(), `Screen${index}`)
    apply({ ...doc, screens: [...doc.screens, next], startScreen: doc.startScreen || next.id })
    setScreenId(next.id)
  }
  const removeScreen = () => {
    if (!screen || !window.confirm(`Delete ${screen.name} and its elements?`)) return
    if (
      doc.screens.some(
        (s) =>
          s.id !== screen.id && s.elements.some((e) => e.action.kind === 'navigate' && e.action.target === screen.id),
      )
    ) {
      setError('This screen is used by navigation buttons. Change their target before deleting it.')
      return
    }
    const screens = doc.screens.filter((s) => s.id !== screen.id)
    apply({ ...doc, screens, startScreen: doc.startScreen === screen.id ? (screens[0]?.id ?? '') : doc.startScreen })
    setScreenId(screens[0]?.id ?? '')
  }
  const addElement = (kind: VisuElement['kind']) => {
    if (!screen || blocked) return
    const element = fitElement(newElement(kind, uuid()), screen)
    editScreen((s) => ({ ...s, elements: [...s.elements, element] }))
    setSelection([element.id])
  }
  const removeElements = () => {
    editScreen((s) => ({ ...s, elements: s.elements.filter((e) => !selection.includes(e.id)) }))
    setSelection([])
  }
  const paste = () => {
    if (!screen || !clipboard.current.length || blocked) return
    const elements = clipboard.current.map((e) =>
      fitElement(
        { ...clone(e), id: uuid(), name: `${e.name}_copy`, x: e.x + screen.grid, y: e.y + screen.grid },
        screen,
      ),
    )
    editScreen((s) => ({ ...s, elements: [...s.elements, ...elements] }))
    setSelection(elements.map((e) => e.id))
  }
  const travel = (back: boolean) => {
    if (blocked) return
    const source = back ? undo : redo,
      next = source[source.length - 1]
    if (!next) return
    if (back) {
      setUndo(source.slice(0, -1))
      setRedo((future) => [...future, clone(doc)])
    } else {
      setRedo(source.slice(0, -1))
      setUndo((past) => [...past, clone(doc)])
    }
    onChange(clone(next))
    setSelection([])
    setError('')
  }
  const reorder = (front: boolean) =>
    editScreen((s) => {
      const selected = s.elements.filter((e) => selection.includes(e.id)),
        others = s.elements.filter((e) => !selection.includes(e.id))
      return { ...s, elements: front ? [...others, ...selected] : [...selected, ...others] }
    })
  const align = (mode: 'left' | 'top' | 'right' | 'bottom') =>
    editScreen((s) => {
      const selected = s.elements.filter((e) => selection.includes(e.id))
      if (selected.length < 2) return s
      const edge =
        mode === 'left'
          ? Math.min(...selected.map((e) => e.x))
          : mode === 'top'
            ? Math.min(...selected.map((e) => e.y))
            : mode === 'right'
              ? Math.max(...selected.map((e) => e.x + e.width))
              : Math.max(...selected.map((e) => e.y + e.height))
      return {
        ...s,
        elements: s.elements.map((e) =>
          !selection.includes(e.id)
            ? e
            : {
                ...e,
                ...(mode === 'left'
                  ? { x: edge }
                  : mode === 'top'
                    ? { y: edge }
                    : mode === 'right'
                      ? { x: edge - e.width }
                      : { y: edge - e.height }),
              },
        ),
      }
    })
  const point = (clientX: number, clientY: number) => {
    const rect = svg.current!.getBoundingClientRect()
    return {
      x: (clientX - rect.left) * (screen.width / (rect.width || screen.width * zoom)),
      y: (clientY - rect.top) * (screen.height / (rect.height || screen.height * zoom)),
    }
  }
  const previewAction = (e: VisuElement, pressed: boolean) => {
    if (!preview || e.action.kind === 'none') return
    if (e.bindings.enabled && valueAt(values, e.bindings.enabled) !== true) return
    if (e.action.kind === 'navigate') {
      if (pressed && !errors.length) setScreenId(e.action.target)
      return
    }
    const action = e.action,
      target = symbols.find((s) => s.path.toLowerCase() === action.target.toLowerCase())
    if (!target?.writable || errors.length) return
    if (action.kind === 'momentary') setValues((v) => ({ ...v, [target.path]: pressed }))
    else if (pressed && action.kind === 'toggle') setValues((v) => ({ ...v, [target.path]: !valueAt(v, target.path) }))
    else if (pressed && action.kind === 'set') setValues((v) => ({ ...v, [target.path]: action.value }))
  }
  const bindSelect = (
    label: string,
    value: string,
    change: (path: string) => void,
    boolOnly = false,
    numericOnly = false,
    writable = false,
  ) => (
    <label className='flex flex-col gap-1'>
      {label}
      <select className={control} aria-label={label} value={value} onChange={(e) => change(e.target.value)}>
        <option value=''>Unbound</option>
        {value && !symbols.some((s) => s.path === value) && <option value={value}>{value} (unresolved)</option>}
        {symbols
          .filter(
            (s) =>
              (!boolOnly || s.type === 'BOOL') && (!numericOnly || isNumericType(s.type)) && (!writable || s.writable),
          )
          .map((s) => (
            <option key={s.path} value={s.path}>
              {s.path} : {s.type}
              {s.writable ? '' : ' (read-only)'}
            </option>
          ))}
      </select>
    </label>
  )
  const numeric = (
    label: string,
    value: number,
    change: (value: number) => void,
    min: number,
    max: number,
    step = 1,
  ) => <NumericField key={label} label={label} value={value} change={change} min={min} max={max} step={step} />
  const exportJson = () => {
    try {
      const content = exportVisualization(doc, symbols),
        url = URL.createObjectURL(new Blob([content], { type: 'application/json' }))
      const a = window.document.createElement('a')
      a.href = url
      a.download = 'targetvisu.json'
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  const importJson = async (file: File) => {
    if (file.size > 4 * 1024 * 1024) {
      setError('JSON exceeds 4 MiB')
      return
    }
    try {
      const imported = TargetVisuSchema.parse(JSON.parse(await file.text()))
      if (doc.screens.length && !window.confirm('Replace all visualization screens?')) return
      apply(imported)
      setScreenId(imported.startScreen)
      setSelection([])
    } catch {
      setError('Invalid TargetVisu JSON or unsupported format version. Current screens are unchanged.')
    }
  }
  return (
    <div
      className='flex h-full min-h-[480px] flex-col gap-2 bg-slate-100 p-3 text-slate-900 dark:bg-neutral-950 dark:text-slate-100'
      data-testid='targetvisu-designer'
      onKeyDown={(e) => {
        if ((e.target as HTMLElement).closest('input,select,textarea') || blocked) return
        const command = e.ctrlKey || e.metaKey
        if (command && e.key.toLowerCase() === 'z') {
          e.preventDefault()
          travel(!e.shiftKey)
        } else if (command && e.key.toLowerCase() === 'y') {
          e.preventDefault()
          travel(false)
        } else if (command && e.key.toLowerCase() === 'c') {
          e.preventDefault()
          clipboard.current = clone(screen?.elements.filter((v) => selection.includes(v.id)) ?? [])
        } else if (command && e.key.toLowerCase() === 'v') {
          e.preventDefault()
          paste()
        } else if (e.key === 'Delete') {
          e.preventDefault()
          removeElements()
        } else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key) && screen) {
          e.preventDefault()
          const step = e.shiftKey ? screen.grid : 1
          editScreen((s) => ({
            ...s,
            elements: s.elements.map((v) =>
              selection.includes(v.id)
                ? fitElement(
                    {
                      ...v,
                      x: v.x + (e.key === 'ArrowRight' ? step : e.key === 'ArrowLeft' ? -step : 0),
                      y: v.y + (e.key === 'ArrowDown' ? step : e.key === 'ArrowUp' ? -step : 0),
                    },
                    s,
                  )
                : v,
            ),
          }))
        }
      }}
    >
      <div className='flex flex-wrap items-center gap-2'>
        <strong className='mr-3 text-sm'>
          TargetVisu <span className='font-normal text-slate-500'>Native X11 · Editor v0.4</span>
        </strong>
        <button
          className={button}
          disabled={readOnly}
          onClick={() => {
            setPreview(!preview)
            setSelection([])
          }}
        >
          {preview ? 'Design' : 'Preview'}
        </button>
        <span className='text-xs text-slate-500'>
          {preview
            ? 'Preview uses local test values. No PLC connection.'
            : 'Ctrl+S saves with the project · Upload includes TargetVisu'}
        </span>
        <div className='ml-auto flex gap-2'>
          <button className={button} onClick={exportJson}>
            Export JSON
          </button>
          <button className={button} disabled={readOnly} onClick={() => fileInput.current?.click()}>
            Import JSON
          </button>
        </div>
        <input
          type='file'
          accept='.json,application/json'
          className='hidden'
          ref={fileInput}
          aria-label='Import visualization file'
          onChange={(event) => {
            const file = event.target.files?.[0]
            event.target.value = ''
            if (file) void importJson(file)
          }}
        />
      </div>
      {(error || errors.length > 0) && (
        <div
          role='alert'
          className='max-h-24 overflow-auto rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-950'
        >
          {error || errors.join(' · ')}
        </div>
      )}
      <div className='flex min-h-0 flex-1 gap-3'>
        <aside className='flex w-44 shrink-0 flex-col gap-2 overflow-auto rounded bg-white p-3 dark:bg-slate-900'>
          <div className='flex justify-between text-xs font-semibold'>
            <span>Screens</span>
            <button className={button} disabled={blocked || doc.screens.length >= 64} onClick={addScreen}>
              + Screen
            </button>
          </div>
          {doc.screens.map((s) => (
            <button
              key={s.id}
              className={`${button} text-left ${s.id === screen?.id ? 'border-blue-500 bg-blue-50' : ''}`}
              onClick={() => setScreenId(s.id)}
            >
              {s.id === doc.startScreen ? '★ ' : ''}
              {s.name}
            </button>
          ))}
          <fieldset disabled={blocked || !screen} className='mt-3 flex flex-col gap-1'>
            <legend className='mb-2 text-xs font-semibold'>Primitives</legend>
            {KINDS.map((kind) => (
              <button
                type='button'
                key={kind}
                className={`${button} text-left capitalize`}
                onClick={() => addElement(kind)}
              >
                + {kind}
              </button>
            ))}
          </fieldset>
          <div className='mt-3 text-xs font-semibold'>Layers — front first</div>
          {screen?.elements
            .slice()
            .reverse()
            .map((e) => (
              <button
                key={e.id}
                className={`${button} text-left ${selection.includes(e.id) ? 'border-blue-500' : ''}`}
                onClick={() => {
                  if (!preview) setSelection([e.id])
                }}
              >
                {e.name}
              </button>
            ))}
        </aside>
        <main className='flex min-w-0 flex-1 flex-col gap-2'>
          <div className='flex flex-wrap items-center gap-1'>
            <button className={button} disabled={blocked || !undo.length} onClick={() => travel(true)}>
              Undo
            </button>
            <button className={button} disabled={blocked || !redo.length} onClick={() => travel(false)}>
              Redo
            </button>
            <button
              className={button}
              disabled={blocked || !selection.length}
              onClick={() => {
                clipboard.current = clone(screen.elements.filter((e) => selection.includes(e.id)))
                paste()
              }}
            >
              Duplicate
            </button>
            <button className={button} disabled={blocked || !selection.length} onClick={removeElements}>
              Delete
            </button>
            <button className={button} disabled={blocked || !selection.length} onClick={() => reorder(true)}>
              To front
            </button>
            <button className={button} disabled={blocked || !selection.length} onClick={() => reorder(false)}>
              To back
            </button>
            {(['left', 'top', 'right', 'bottom'] as const).map((mode) => (
              <button
                key={mode}
                className={button}
                disabled={blocked || selection.length < 2}
                onClick={() => align(mode)}
              >
                Align {mode}
              </button>
            ))}
            <label className='ml-auto flex gap-1 text-xs'>
              <input type='checkbox' checked={snap} disabled={preview} onChange={(e) => setSnap(e.target.checked)} />
              Grid
            </label>
            <select
              className={control}
              aria-label='Zoom'
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
            >
              {[0.5, 0.75, 1, 1.25, 1.5, 2].map((z) => (
                <option key={z} value={z}>
                  {z * 100}%
                </option>
              ))}
            </select>
          </div>
          <div className='min-h-0 flex-1 overflow-auto rounded border border-slate-300 bg-slate-200 p-4 dark:bg-slate-800'>
            {!screen ? (
              <div className='flex h-64 flex-col items-center justify-center gap-3 text-sm'>
                <span>Create the first TargetVisu screen</span>
                <button className={button} disabled={readOnly} onClick={addScreen}>
                  Create screen
                </button>
              </div>
            ) : (
              <svg
                ref={svg}
                role='application'
                aria-label='Visualization canvas'
                tabIndex={0}
                width={screen.width * zoom}
                height={screen.height * zoom}
                viewBox={`0 0 ${screen.width} ${screen.height}`}
                className='shadow-md outline-none'
                style={{ background: screen.background, touchAction: 'none', display: 'block' }}
                onPointerDown={(e) => {
                  if (e.target === svg.current && !preview) setSelection([])
                }}
                onPointerMove={(e) => {
                  const gesture = drag.current
                  if (!gesture || blocked) return
                  const at = point(e.clientX, e.clientY),
                    round = (n: number) => (snap ? Math.round(n / screen.grid) * screen.grid : n)
                  let dx = round(at.x - gesture.start.x),
                    dy = round(at.y - gesture.start.y)
                  if (!gesture.resize) {
                    const items = gesture.screen.elements.filter((v) => gesture.ids.includes(v.id))
                    dx = Math.max(
                      -Math.min(...items.map((v) => v.x)),
                      Math.min(dx, Math.min(...items.map((v) => screen.width - v.x - v.width))),
                    )
                    dy = Math.max(
                      -Math.min(...items.map((v) => v.y)),
                      Math.min(dy, Math.min(...items.map((v) => screen.height - v.y - v.height))),
                    )
                  }
                  const moved = {
                    ...gesture.screen,
                    elements: gesture.screen.elements.map((v) =>
                      !gesture.ids.includes(v.id)
                        ? v
                        : fitElement(
                            {
                              ...v,
                              ...(gesture.resize
                                ? {
                                    width: Math.max(8, Math.min(gesture.screen.width - v.x, v.width + dx)),
                                    height: Math.max(8, Math.min(gesture.screen.height - v.y, v.height + dy)),
                                  }
                                : { x: v.x + dx, y: v.y + dy }),
                            },
                            gesture.screen,
                          ),
                    ),
                  }
                  apply(
                    { ...gesture.base, screens: gesture.base.screens.map((s) => (s.id === screen.id ? moved : s)) },
                    false,
                  )
                }}
                onPointerUp={() => {
                  const gesture = drag.current
                  drag.current = null
                  if (gesture && JSON.stringify(gesture.base) !== JSON.stringify(doc)) {
                    setUndo((past) => [...past.slice(-99), gesture.base])
                    setRedo([])
                  }
                }}
                onPointerCancel={() => {
                  if (drag.current) {
                    onChange(drag.current.base)
                    drag.current = null
                  }
                }}
              >
                <defs>
                  <pattern
                    id={`grid-${screen.id}`}
                    width={screen.grid}
                    height={screen.grid}
                    patternUnits='userSpaceOnUse'
                  >
                    <path
                      d={`M ${screen.grid} 0 L 0 0 0 ${screen.grid}`}
                      fill='none'
                      stroke='#94a3b8'
                      strokeWidth='0.4'
                    />
                  </pattern>
                </defs>
                {!preview && snap && (
                  <rect
                    width={screen.width}
                    height={screen.height}
                    fill={`url(#grid-${screen.id})`}
                    pointerEvents='none'
                  />
                )}
                {screen.elements.map((element) => {
                  const visible =
                    !preview || !element.bindings.visible || valueAt(values, element.bindings.visible) === true
                  if (!visible) return null
                  return (
                    <g
                      key={element.id}
                      data-testid={`element-${element.id}`}
                      opacity={
                        preview && element.bindings.enabled && valueAt(values, element.bindings.enabled) !== true
                          ? 0.4
                          : 1
                      }
                      onPointerDown={(e) => {
                        e.stopPropagation()
                        svg.current?.focus()
                        if (preview) {
                          e.currentTarget.setPointerCapture?.(e.pointerId)
                          previewAction(element, true)
                          return
                        }
                        if (readOnly) return
                        const toggle = e.shiftKey || e.ctrlKey || e.metaKey
                        const ids = toggle
                          ? selection.includes(element.id)
                            ? selection.filter((id) => id !== element.id)
                            : [...selection, element.id]
                          : selection.includes(element.id)
                            ? selection
                            : [element.id]
                        setSelection(ids)
                        if (!ids.length) return
                        svg.current?.setPointerCapture?.(e.pointerId)
                        drag.current = {
                          base: clone(doc),
                          screen: clone(screen),
                          ids,
                          start: point(e.clientX, e.clientY),
                          resize: false,
                        }
                      }}
                      onPointerUp={() => previewAction(element, false)}
                      onPointerCancel={() => previewAction(element, false)}
                      onLostPointerCapture={() => previewAction(element, false)}
                    >
                      <rect
                        x={element.x}
                        y={element.y}
                        width={element.width}
                        height={element.height}
                        fill='transparent'
                      />
                      <RenderElement element={element} preview={preview} values={values} />
                    </g>
                  )
                })}
                {!preview &&
                  screen.elements
                    .filter((e) => selection.includes(e.id))
                    .map((e) => (
                      <rect
                        key={e.id}
                        x={e.x - 2}
                        y={e.y - 2}
                        width={e.width + 4}
                        height={e.height + 4}
                        fill='none'
                        stroke='#2563eb'
                        strokeDasharray='4 2'
                        pointerEvents='none'
                      />
                    ))}
                {!blocked && selection.length === 1 && current && (
                  <rect
                    data-testid='resize-handle'
                    x={current.x + current.width - 5}
                    y={current.y + current.height - 5}
                    width={10}
                    height={10}
                    fill='#2563eb'
                    style={{ cursor: 'nwse-resize' }}
                    onPointerDown={(e) => {
                      e.stopPropagation()
                      svg.current?.setPointerCapture?.(e.pointerId)
                      drag.current = {
                        base: clone(doc),
                        screen: clone(screen),
                        ids: selection,
                        start: point(e.clientX, e.clientY),
                        resize: true,
                      }
                    }}
                  />
                )}
              </svg>
            )}
          </div>
          <div className='text-xs text-slate-500'>
            {screen
              ? `${screen.width} × ${screen.height} · ${screen.elements.length} elements · ${selection.length} selected`
              : ''}{' '}
            · Shift-click: multi-select · Arrows: move · Ctrl+C/V: copy/paste
          </div>
        </main>
        <aside className='flex w-64 shrink-0 flex-col gap-3 overflow-auto rounded bg-white p-3 text-xs dark:bg-slate-900'>
          {preview ? (
            <>
              <strong>Local preview values</strong>
              <p>No values are sent to the PLC.</p>
              {symbols.map((s) => (
                <label key={s.path} className='flex flex-col gap-1'>
                  {s.path} : {s.type}
                  {s.type === 'BOOL' ? (
                    <input
                      aria-label={`Preview ${s.path}`}
                      type='checkbox'
                      checked={valueAt(values, s.path) === true}
                      onChange={(e) => setValues({ ...values, [s.path]: e.target.checked })}
                    />
                  ) : (
                    <input
                      className={control}
                      aria-label={`Preview ${s.path}`}
                      type={isNumericType(s.type) ? 'number' : 'text'}
                      value={String(values[s.path] ?? '')}
                      onChange={(e) =>
                        setValues({
                          ...values,
                          [s.path]: isNumericType(s.type) ? Number(e.target.value) : e.target.value,
                        })
                      }
                    />
                  )}
                </label>
              ))}
              {screen?.elements
                .filter((e) => e.kind === 'number' && e.action.kind === 'write')
                .map((e) => (
                  <label key={e.id}>
                    Input: {e.name}
                    <input
                      type='number'
                      aria-label={`Input ${e.name}`}
                      className={control}
                      min={e.minimum}
                      max={e.maximum}
                      onChange={(event) => {
                        const n = Number(event.target.value),
                          target = symbols.find((s) => s.path === e.action.target)
                        if (
                          target?.writable &&
                          !errors.length &&
                          Number.isFinite(n) &&
                          n >= e.minimum &&
                          n <= e.maximum &&
                          (!e.bindings.enabled || valueAt(values, e.bindings.enabled) === true) &&
                          (!e.bindings.visible || valueAt(values, e.bindings.visible) === true)
                        )
                          setValues({ ...values, [target.path]: n })
                      }}
                    />
                  </label>
                ))}
            </>
          ) : (
            <fieldset disabled={readOnly} className='flex flex-col gap-3'>
              <legend className='mb-3 font-semibold'>{current ? 'Element properties' : 'Screen properties'}</legend>
              {current ? (
                <>
                  <label className='flex flex-col gap-1'>
                    Element name
                    <input
                      className={control}
                      aria-label='Element name'
                      value={current.name}
                      onChange={(e) => patchElement({ name: e.target.value })}
                    />
                  </label>
                  {(['x', 'y', 'width', 'height'] as const).map((key) =>
                    numeric(
                      key,
                      current[key],
                      (n) => patchElement({ [key]: n }),
                      key === 'width' || key === 'height' ? 8 : 0,
                      key === 'x' || key === 'width' ? screen.width : screen.height,
                    ),
                  )}
                  <label className='flex flex-col gap-1'>
                    Text
                    <input
                      className={control}
                      aria-label='Text'
                      value={current.text}
                      onChange={(e) => patchElement({ text: e.target.value })}
                    />
                  </label>
                  {current.kind === 'line' && (
                    <label className='flex flex-col gap-1'>
                      Line direction
                      <select
                        className={control}
                        aria-label='Line direction'
                        value={current.lineDirection}
                        onChange={(event) =>
                          patchElement({ lineDirection: event.target.value as VisuElement['lineDirection'] })
                        }
                      >
                        {['horizontal', 'vertical', 'diagonal-down', 'diagonal-up'].map((direction) => (
                          <option key={direction} value={direction}>
                            {direction}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  {numeric('Font size', current.fontSize, (n) => patchElement({ fontSize: n }), 6, 200)}
                  {numeric('Stroke width', current.strokeWidth, (n) => patchElement({ strokeWidth: n }), 0, 20)}
                  {(['fill', 'activeFill', 'stroke', 'textColor'] as const).map((key) => (
                    <label key={key} className='flex justify-between'>
                      {key}
                      <input
                        type='color'
                        aria-label={key}
                        value={current[key]}
                        onChange={(e) => patchElement({ [key]: e.target.value })}
                      />
                    </label>
                  ))}
                  {bindSelect(
                    'Value variable',
                    current.bindings.value,
                    (value) => patchElement({ bindings: { ...current.bindings, value } }),
                    current.kind === 'indicator',
                    current.kind === 'number',
                  )}
                  {bindSelect(
                    'Visible when TRUE',
                    current.bindings.visible,
                    (visible) => patchElement({ bindings: { ...current.bindings, visible } }),
                    true,
                  )}
                  {bindSelect(
                    'Enabled when TRUE',
                    current.bindings.enabled,
                    (enabled) => patchElement({ bindings: { ...current.bindings, enabled } }),
                    true,
                  )}
                  {(current.kind === 'button' || current.kind === 'number') && (
                    <>
                      <label className='flex flex-col gap-1'>
                        Action
                        <select
                          className={control}
                          aria-label='Action'
                          value={current.action.kind}
                          onChange={(e) =>
                            patchElement({
                              action: {
                                ...current.action,
                                kind: e.target.value as VisuElement['action']['kind'],
                                target:
                                  e.target.value === 'navigate'
                                    ? (doc.screens.find((s) => s.id !== screen.id)?.id ?? screen.id)
                                    : current.action.kind === 'navigate'
                                      ? ''
                                      : current.action.target,
                              },
                            })
                          }
                        >
                          {(current.kind === 'number'
                            ? ['none', 'write']
                            : ['none', 'set', 'toggle', 'momentary', 'navigate']
                          ).map((kind) => (
                            <option key={kind} value={kind}>
                              {kind === 'navigate' ? 'Перейти на экран' : kind}
                            </option>
                          ))}
                        </select>
                      </label>
                      {current.action.kind === 'navigate' && (
                        <label className='flex flex-col gap-1'>
                          Целевой экран
                          <select
                            className={control}
                            aria-label='Target screen'
                            value={current.action.target}
                            onChange={(e) => patchElement({ action: { ...current.action, target: e.target.value } })}
                          >
                            {!doc.screens.some((s) => s.id === current.action.target) && (
                              <option value={current.action.target}>Экран не найден</option>
                            )}
                            {doc.screens.map((s) => (
                              <option key={s.id} value={s.id}>
                                {s.name}
                              </option>
                            ))}
                          </select>
                        </label>
                      )}
                      {current.action.kind !== 'none' &&
                        current.action.kind !== 'navigate' &&
                        bindSelect(
                          'Action target',
                          current.action.target,
                          (target) => {
                            const spec = symbols.find((s) => s.path === target)
                            patchElement({
                              action: {
                                ...current.action,
                                target,
                                value: spec?.type === 'BOOL' ? true : spec && isNumericType(spec.type) ? 0 : '',
                              },
                            })
                          },
                          ['toggle', 'momentary'].includes(current.action.kind),
                          current.action.kind === 'write',
                          true,
                        )}
                      {current.action.kind === 'set' && (
                        <label className='flex flex-col gap-1'>
                          Set value
                          {symbols.find((s) => s.path === current.action.target)?.type === 'BOOL' ? (
                            <select
                              className={control}
                              aria-label='Set value'
                              value={String(current.action.value)}
                              onChange={(e) =>
                                patchElement({ action: { ...current.action, value: e.target.value === 'true' } })
                              }
                            >
                              <option value='true'>TRUE</option>
                              <option value='false'>FALSE</option>
                            </select>
                          ) : (
                            <input
                              className={control}
                              aria-label='Set value'
                              value={String(current.action.value)}
                              onChange={(e) => {
                                const spec = symbols.find((s) => s.path === current.action.target),
                                  value = spec && isNumericType(spec.type) ? Number(e.target.value) : e.target.value
                                if (typeof value !== 'number' || Number.isFinite(value))
                                  patchElement({ action: { ...current.action, value } })
                              }}
                            />
                          )}
                        </label>
                      )}
                    </>
                  )}
                  {current.kind === 'number' && (
                    <>
                      {numeric('Decimals', current.decimals, (n) => patchElement({ decimals: n }), 0, 6)}
                      {numeric(
                        'Minimum',
                        current.minimum,
                        (n) => patchElement({ minimum: n }),
                        -1e12,
                        current.maximum,
                        0.1,
                      )}
                      {numeric(
                        'Maximum',
                        current.maximum,
                        (n) => patchElement({ maximum: n }),
                        current.minimum,
                        1e12,
                        0.1,
                      )}
                    </>
                  )}
                </>
              ) : screen ? (
                <>
                  <label className='flex flex-col gap-1'>
                    Screen name
                    <input
                      className={control}
                      aria-label='Screen name'
                      value={screen.name}
                      onChange={(e) => editScreen((s) => ({ ...s, name: e.target.value }))}
                    />
                  </label>
                  {numeric(
                    'Screen width',
                    screen.width,
                    (n) =>
                      editScreen((s) => {
                        const next = { ...s, width: n }
                        return { ...next, elements: s.elements.map((e) => fitElement(e, next)) }
                      }),
                    160,
                    8192,
                  )}
                  {numeric(
                    'Screen height',
                    screen.height,
                    (n) =>
                      editScreen((s) => {
                        const next = { ...s, height: n }
                        return { ...next, elements: s.elements.map((e) => fitElement(e, next)) }
                      }),
                    120,
                    8192,
                  )}
                  {numeric('Grid size', screen.grid, (n) => editScreen((s) => ({ ...s, grid: n })), 1, 100)}
                  {numeric('Refresh (ms)', doc.refreshMs, (refreshMs) => apply({ ...doc, refreshMs }), 100, 5000)}
                  <label className='flex justify-between'>
                    Background
                    <input
                      type='color'
                      aria-label='Background'
                      value={screen.background}
                      onChange={(e) => editScreen((s) => ({ ...s, background: e.target.value }))}
                    />
                  </label>
                  <button
                    className={button}
                    disabled={screen.id === doc.startScreen}
                    onClick={() => apply({ ...doc, startScreen: screen.id })}
                  >
                    Set as start screen
                  </button>
                  <button
                    className={button}
                    onClick={() => {
                      let suffix = doc.screens.length + 1
                      while (doc.screens.some((s) => s.name.toLowerCase() === `screen${suffix}`)) suffix++
                      const next = {
                        ...clone(screen),
                        id: uuid(),
                        name: `Screen${suffix}`,
                        elements: screen.elements.map((e) => ({ ...clone(e), id: uuid() })),
                      }
                      apply({ ...doc, screens: [...doc.screens, next] })
                      setScreenId(next.id)
                    }}
                  >
                    Duplicate screen
                  </button>
                  <button className={button} onClick={removeScreen}>
                    Delete screen
                  </button>
                </>
              ) : (
                <p>Add a screen to begin.</p>
              )}
            </fieldset>
          )}
        </aside>
      </div>
    </div>
  )
}
