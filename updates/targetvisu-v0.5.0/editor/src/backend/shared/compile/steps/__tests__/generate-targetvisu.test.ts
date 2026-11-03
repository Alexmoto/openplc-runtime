import { createHash } from 'crypto'
import { TextEncoder } from 'util'
import { emptyVisualization, newElement, newScreen } from '../../../../../middleware/shared/targetvisu/model'
import type { PLCProjectData } from '../../../types/PLC/open-plc'
import { generateTargetVisuBundle } from '../generate-targetvisu'

Object.assign(globalThis, { TextEncoder })
const md5 = 'a'.repeat(32)
const hash = async (s: string) => createHash('md5').update(s).digest('hex')
function fixture() {
  const screen = newScreen('screen', 'Main')
  const button = newElement('button', 'button')
  button.action = { kind: 'toggle', target: 'Run', value: true }
  screen.elements.push(button)
  const project = {
    targetVisu: { ...emptyVisualization(), startScreen: screen.id, screens: [screen] },
    configuration: {
      resource: { globalVariables: [{ name: 'Run', type: { definition: 'base-type', value: 'BOOL' } }], instances: [] },
    },
    pous: [],
  } as unknown as PLCProjectData
  const map = { version: 2, md5, leaves: [{ path: 'RUN', type: 'BOOL', size: 1, arrayIdx: 0, elemIdx: 0 }] }
  return { project, map }
}
test('bundle includes matching document hashes and canonical action permissions', async () => {
  const { project, map } = fixture()
  const result = (await generateTargetVisuBundle(project, JSON.stringify(map), md5, hash))!
  expect(JSON.parse(result.deployment)).toEqual({
    version: 1,
    target: 'native-x11',
    programMd5: md5,
    documentMd5: await hash(result.document),
    writableSymbols: ['RUN'],
  })
  expect(JSON.parse(result.document)).toEqual(project.targetVisu)
})
test('no visualization does not require a debug map', async () => {
  expect(await generateTargetVisuBundle({} as PLCProjectData, '', md5, hash)).toBeUndefined()
})
test('rejects mismatched compiled program', async () => {
  const { project, map } = fixture()
  await expect(
    generateTargetVisuBundle(project, JSON.stringify({ ...map, md5: 'b'.repeat(32) }), md5, hash),
  ).rejects.toThrow('mismatch')
})
test('rejects unknown bindings', async () => {
  const { project, map } = fixture()
  project.targetVisu!.screens[0].elements[0].bindings.value = 'Missing'
  await expect(generateTargetVisuBundle(project, JSON.stringify(map), md5, hash)).rejects.toThrow('unknown variable')
})
test('rejects writes to physical inputs and constants', async () => {
  for (const restriction of [{ location: '%IX0.0' }, { flag: 'constant' }]) {
    const { project, map } = fixture()
    Object.assign(project.configuration.resource.globalVariables[0], restriction)
    await expect(generateTargetVisuBundle(project, JSON.stringify(map), md5, hash)).rejects.toThrow('read-only')
  }
})
test('rejects invalid compiled widths and indexes', async () => {
  for (const invalid of [{ size: 2 }, { elemIdx: 65536 }, { arrayIdx: -1 }]) {
    const { project, map } = fixture()
    Object.assign(map.leaves[0], invalid)
    await expect(generateTargetVisuBundle(project, JSON.stringify(map), md5, hash)).rejects.toThrow('unsupported')
  }
})
test('rejects duplicate compiled paths', async () => {
  const { project, map } = fixture()
  map.leaves.push({ ...map.leaves[0], elemIdx: 1 })
  await expect(generateTargetVisuBundle(project, JSON.stringify(map), md5, hash)).rejects.toThrow('ambiguous')
})

test('navigation exports a screen id without granting PLC write permission', async () => {
  const { project, map } = fixture()
  project.targetVisu!.screens.push(newScreen('details', 'Details'))
  project.targetVisu!.screens[0].elements[0].action = { kind: 'navigate', target: 'details', value: true }
  const result = (await generateTargetVisuBundle(project, JSON.stringify(map), md5, hash))!
  expect(JSON.parse(result.deployment).writableSymbols).toEqual([])
  expect(JSON.parse(result.document).screens[0].elements[0].action.target).toBe('details')
  project.targetVisu!.screens.pop()
  await expect(generateTargetVisuBundle(project, JSON.stringify(map), md5, hash)).rejects.toThrow('screen is missing')
})

test('embedded graphic survives upload with a matching manifest and no PLC writes', async () => {
  const { project, map } = fixture()
  const image = newElement('graphic', 'image')
  image.graphic = {
    data: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAYAAAD0In+KAAAAD0lEQVR4nGP4z8DwHwgZAA/5Av4tR4H0AAAAAElFTkSuQmCC',
    fit: 'contain',
  }
  project.targetVisu!.screens[0].elements = [image]
  const result = (await generateTargetVisuBundle(project, JSON.stringify(map), md5, hash))!
  expect(JSON.parse(result.document).screens[0].elements[0].graphic).toEqual(image.graphic)
  expect(JSON.parse(result.deployment).writableSymbols).toEqual([])
  expect(JSON.parse(result.deployment).documentMd5).toBe(await hash(result.document))
})
