// SPDX-License-Identifier: GPL-3.0-only
import { TargetVisuSchema, validateBindings } from '../../../../middleware/shared/targetvisu/model'
import type { ComposeRuntimeV4BundleInput } from '../../../../middleware/shared/utils/library/compose-runtime-v4-bundle'
import type { PLCProjectData } from '../../types/PLC/open-plc'

/** Bind a visualization to the exact compiled program; deny writes unless declared writable. */
export async function generateTargetVisuBundle(
  project: PLCProjectData,
  debugMapContent: string,
  md5: string,
  hashDocument: (content: string) => Promise<string>,
): Promise<ComposeRuntimeV4BundleInput['targetVisu']> {
  if (!project.targetVisu?.screens.length) return undefined
  const document = TargetVisuSchema.parse(project.targetVisu)
  const map = JSON.parse(debugMapContent)
  if (
    map.version !== 2 ||
    !/^[a-f0-9]{32}$/i.test(md5) ||
    map.md5?.toLowerCase() !== md5.toLowerCase() ||
    !Array.isArray(map.leaves)
  )
    throw new Error('TargetVisu: compiled debug map / program mismatch')
  const writable = new Map<string, boolean>()
  const append = (prefix: string, variables: PLCProjectData['pous'][number]['data']['variables'], constant = false) => {
    for (const variable of variables) {
      if (variable.class === 'temp' || variable.class === 'external') continue
      const path = (prefix + variable.name).toLowerCase()
      const allowed = !constant && variable.flag !== 'constant' && !/^%I/i.test(variable.location ?? '')
      writable.set(path, writable.has(path) ? false : allowed)
    }
  }
  append('', project.configuration.resource.globalVariables as PLCProjectData['pous'][number]['data']['variables'])
  for (const list of project.globalVariableLists ?? [])
    append(`${list.name}.`, list.variables, /\bCONSTANT\b/i.test(list.qualifier ?? ''))
  for (const instance of project.configuration.resource.instances) {
    const pou = project.pous.find(
      (p) => p.type === 'program' && p.data.name.toLowerCase() === instance.program.toLowerCase(),
    )
    if (pou) append(`${instance.name}.`, pou.data.variables)
  }
  const widths: Record<string, number> = {
    BOOL: 1,
    SINT: 1,
    USINT: 1,
    BYTE: 1,
    INT: 2,
    UINT: 2,
    WORD: 2,
    DINT: 4,
    UDINT: 4,
    DWORD: 4,
    REAL: 4,
    LINT: 8,
    ULINT: 8,
    LWORD: 8,
    LREAL: 8,
  }
  const leaves = new Map<string, { path: string; type: string; writable: boolean; size: number }>()
  const addresses = new Set<string>()
  for (const leaf of map.leaves) {
    if (typeof leaf.path !== 'string' || typeof leaf.type !== 'string')
      throw new Error('TargetVisu: invalid compiled symbol')
    const key = leaf.path.toLowerCase(),
      address = `${leaf.arrayIdx}:${leaf.elemIdx}`
    if (leaves.has(key) || addresses.has(address)) throw new Error('TargetVisu: ambiguous compiled symbol')
    addresses.add(address)
    leaves.set(key, { ...leaf, type: leaf.type.toUpperCase(), writable: writable.get(key) === true })
  }
  const errors = validateBindings(document, [...leaves.values()])
  if (errors.length) throw new Error(`TargetVisu: ${errors.join('\n')}`)
  const used = new Set<string>(),
    writes = new Set<string>()
  for (const screen of document.screens)
    for (const element of screen.elements) {
      for (const path of Object.values(element.bindings)) if (path) used.add(path.toLowerCase())
      if (element.action.kind !== 'none' && element.action.kind !== 'navigate') {
        const key = element.action.target.toLowerCase()
        used.add(key)
        writes.add(leaves.get(key)!.path)
        const leaf = leaves.get(key)!
        if (element.action.kind === 'set' && typeof element.action.value === 'number') {
          const value = element.action.value,
            bits = widths[leaf.type] * 8
          const signed = ['SINT', 'INT', 'DINT', 'LINT'].includes(leaf.type)
          if (
            leaf.type === 'REAL'
              ? !Number.isFinite(Math.fround(value))
              : leaf.type !== 'LREAL' &&
                (!Number.isInteger(value) ||
                  value < (signed ? -(2 ** (bits - 1)) : 0) ||
                  value >= 2 ** (bits - (signed ? 1 : 0)))
          )
            throw new Error(`TargetVisu: set value outside ${leaf.type} range`)
        }
      }
    }
  if (used.size > 1000) throw new Error('TargetVisu: too many bound variables')
  for (const key of used) {
    const leaf = leaves.get(key)!,
      raw = map.leaves.find((l: { path: string }) => l.path.toLowerCase() === key)
    if (
      !widths[leaf.type] ||
      leaf.size !== widths[leaf.type] ||
      !Number.isInteger(raw.arrayIdx) ||
      raw.arrayIdx < 0 ||
      raw.arrayIdx > 255 ||
      !Number.isInteger(raw.elemIdx) ||
      raw.elemIdx < 0 ||
      raw.elemIdx > 65535
    )
      throw new Error(`TargetVisu: unsupported compiled variable ${leaf.path}`)
  }
  const text = JSON.stringify(document, null, 2) + '\n'
  // Every UTF-16 code unit consumes at most three UTF-8 bytes; use the actual encoded size.
  if (new TextEncoder().encode(text).length > 4 * 1024 * 1024) throw new Error('TargetVisu: document exceeds 4 MiB')
  const documentMd5 = (await hashDocument(text)).toLowerCase()
  if (!/^[a-f0-9]{32}$/.test(documentMd5)) throw new Error('TargetVisu: invalid document hash')
  return {
    document: text,
    deployment:
      JSON.stringify(
        {
          version: 1,
          target: 'native-x11',
          programMd5: md5.toLowerCase(),
          documentMd5,
          writableSymbols: [...writes].sort(),
        },
        null,
        2,
      ) + '\n',
  }
}
