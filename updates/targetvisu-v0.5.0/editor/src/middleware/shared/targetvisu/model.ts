// SPDX-License-Identifier: GPL-3.0-only
import { z } from 'zod'
import { graphicDimensions, MAX_GRAPHIC_BYTES, PNG_PREFIX } from './graphics'

const color = z.string().regex(/^#[0-9a-fA-F]{6}$/)
const symbol = z.string().max(256)
export const ElementSchema = z
  .object({
    id: z.string().min(1).max(128),
    name: z.string().min(1).max(80),
    kind: z.enum(['rectangle', 'ellipse', 'line', 'text', 'indicator', 'button', 'number', 'graphic']),
    graphic: z
      .object({
        data: z
          .string()
          .max(PNG_PREFIX.length + 4 * Math.ceil(MAX_GRAPHIC_BYTES / 3))
          .refine((data) => data === '' || !!graphicDimensions(data), 'Invalid embedded PNG'),
        fit: z.enum(['contain', 'cover', 'stretch']),
      })
      .strict()
      .optional(),
    lineDirection: z.enum(['horizontal', 'vertical', 'diagonal-down', 'diagonal-up']).default('horizontal'),
    x: z.number().finite().min(0).max(8192),
    y: z.number().finite().min(0).max(8192),
    width: z.number().finite().min(8).max(8192),
    height: z.number().finite().min(8).max(8192),
    fill: color,
    activeFill: color,
    stroke: color,
    strokeWidth: z.number().min(0).max(20),
    textColor: color,
    fontSize: z.number().int().min(6).max(200),
    text: z.string().max(1024),
    decimals: z.number().int().min(0).max(6),
    minimum: z.number().finite(),
    maximum: z.number().finite(),
    bindings: z.object({ value: symbol, visible: symbol, enabled: symbol }),
    action: z.object({
      kind: z.enum(['none', 'set', 'toggle', 'momentary', 'write', 'navigate']),
      target: symbol,
      value: z.union([z.boolean(), z.number().finite(), z.string().max(256)]),
    }),
  })
  .strict()
export const ScreenSchema = z
  .object({
    id: z.string().min(1).max(128),
    name: z.string().regex(/^[A-Za-z][A-Za-z0-9_]{0,63}$/),
    width: z.number().int().min(160).max(8192),
    height: z.number().int().min(120).max(8192),
    background: color,
    grid: z.number().int().min(1).max(100),
    elements: z.array(ElementSchema).max(1000),
  })
  .strict()
export const TargetVisuSchema = z
  .object({
    version: z.literal(1),
    target: z.literal('native-x11'),
    refreshMs: z.number().int().min(100).max(5000),
    startScreen: z.string(),
    screens: z.array(ScreenSchema).max(64),
  })
  .strict()
  .superRefine((doc, ctx) => {
    const ids = new Set<string>(),
      names = new Set<string>()
    for (const screen of doc.screens) {
      if (ids.has(screen.id) || names.has(screen.name.toLowerCase()))
        ctx.addIssue({ code: 'custom', message: 'Duplicate screen id or name' })
      ids.add(screen.id)
      names.add(screen.name.toLowerCase())
      for (const element of screen.elements) {
        if (ids.has(element.id)) ctx.addIssue({ code: 'custom', message: 'Duplicate element id' })
        ids.add(element.id)
        if (element.x + element.width > screen.width || element.y + element.height > screen.height)
          ctx.addIssue({ code: 'custom', message: `${screen.name}/${element.name}: element exceeds screen bounds` })
        if (element.minimum > element.maximum)
          ctx.addIssue({ code: 'custom', message: `${element.name}: minimum exceeds maximum` })
      }
    }
    if (doc.screens.length ? !doc.screens.some((s) => s.id === doc.startScreen) : doc.startScreen !== '')
      ctx.addIssue({ code: 'custom', message: 'Start screen is missing' })
  })
export type TargetVisuDocument = z.infer<typeof TargetVisuSchema>
export type VisuScreen = z.infer<typeof ScreenSchema>
export type VisuElement = z.infer<typeof ElementSchema>
export type VisuValue = boolean | number | string
export interface VisuSymbol {
  path: string
  type: string
  writable: boolean
}
const numericTypes = new Set([
  'SINT',
  'INT',
  'DINT',
  'LINT',
  'USINT',
  'UINT',
  'UDINT',
  'ULINT',
  'REAL',
  'LREAL',
  'BYTE',
  'WORD',
  'DWORD',
  'LWORD',
])
export const isNumericType = (type: string) => numericTypes.has(type.toUpperCase())
export const emptyVisualization = (): TargetVisuDocument => ({
  version: 1,
  target: 'native-x11',
  refreshMs: 250,
  startScreen: '',
  screens: [],
})
export function newScreen(id: string, name: string): VisuScreen {
  return { id, name, width: 800, height: 480, background: '#f3f5f7', grid: 10, elements: [] }
}
export function newElement(kind: VisuElement['kind'], id: string): VisuElement {
  return {
    id,
    name: `${kind}_${id.slice(0, 6)}`,
    kind,
    ...(kind === 'graphic' ? { graphic: { data: '', fit: 'contain' as const } } : {}),
    lineDirection: 'horizontal',
    x: 20,
    y: 20,
    width: kind === 'indicator' ? 48 : 140,
    height: kind === 'line' ? 8 : kind === 'graphic' ? 100 : 48,
    fill: kind === 'button' ? '#2563eb' : '#dbe2ea',
    activeFill: '#22c55e',
    stroke: '#475569',
    strokeWidth: 1,
    textColor: kind === 'button' ? '#ffffff' : '#172033',
    fontSize: 18,
    text: kind === 'text' ? 'Text' : kind === 'button' ? 'Button' : '',
    decimals: 1,
    minimum: 0,
    maximum: 100,
    bindings: { value: '', visible: '', enabled: '' },
    action: { kind: 'none', target: '', value: true },
  }
}
export function fitElement(element: VisuElement, screen: VisuScreen): VisuElement {
  const width = Math.min(screen.width, Math.max(8, element.width))
  const height = Math.min(screen.height, Math.max(8, element.height))
  return {
    ...element,
    width,
    height,
    x: Math.min(screen.width - width, Math.max(0, element.x)),
    y: Math.min(screen.height - height, Math.max(0, element.y)),
  }
}
export function validateBindings(doc: TargetVisuDocument, symbols: readonly VisuSymbol[]): string[] {
  const errors: string[] = [],
    byPath = new Map(symbols.map((s) => [s.path.toLowerCase(), s]))
  for (const screen of doc.screens)
    for (const element of screen.elements) {
      const label = `${screen.name}/${element.name}`
      if (element.kind === 'graphic' && !element.graphic?.data) errors.push(`${label}: image is missing`)
      for (const [property, path] of Object.entries(element.bindings)) {
        if (!path) continue
        const found = byPath.get(path.toLowerCase())
        if (!found) {
          errors.push(`${label}: unknown variable ${path}`)
          continue
        }
        const boolRequired = property !== 'value' || element.kind === 'indicator'
        if (boolRequired && found.type.toUpperCase() !== 'BOOL') errors.push(`${label}: ${property} requires BOOL`)
        if (property === 'value' && element.kind === 'number' && !isNumericType(found.type))
          errors.push(`${label}: number requires numeric value`)
      }
      const action = element.action
      if (element.kind === 'graphic' && action.kind !== 'none') errors.push(`${label}: graphic view is display-only`)
      if (action.kind === 'none') continue
      if (action.kind === 'navigate') {
        if (element.kind !== 'button') errors.push(`${label}: navigate requires a button`)
        if (!doc.screens.some((s) => s.id === action.target))
          errors.push(`${label}: navigation target screen is missing`)
        continue
      }
      const found = byPath.get(action.target.toLowerCase())
      if (!found) {
        errors.push(`${label}: unknown action target ${action.target || '(empty)'}`)
        continue
      }
      if (!found.writable) errors.push(`${label}: ${action.target} is read-only`)
      if (['toggle', 'momentary'].includes(action.kind) && found.type.toUpperCase() !== 'BOOL')
        errors.push(`${label}: ${action.kind} requires BOOL`)
      if (action.kind === 'write' && (element.kind !== 'number' || !isNumericType(found.type)))
        errors.push(`${label}: numeric write requires a numeric field and target`)
      if (action.kind === 'set') {
        const expected =
          found.type.toUpperCase() === 'BOOL' ? 'boolean' : isNumericType(found.type) ? 'number' : 'string'
        if (typeof action.value !== expected) errors.push(`${label}: set value must be ${expected}`)
      }
    }
  return errors
}
export function exportVisualization(doc: TargetVisuDocument, symbols: readonly VisuSymbol[]): string {
  const parsed = TargetVisuSchema.parse(doc)
  const errors = validateBindings(parsed, symbols)
  if (errors.length) throw new Error(errors.join('\n'))
  return JSON.stringify(parsed, null, 2) + '\n'
}
