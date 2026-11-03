import { graphicDimensions, PNG_PREFIX } from '../graphics'
import { emptyVisualization, exportVisualization, newElement, newScreen, TargetVisuSchema } from '../model'

function pngHeader(width: number, height: number) {
  const bytes = new Uint8Array(33)
  bytes.set([137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82])
  const view = new DataView(bytes.buffer)
  view.setUint32(16, width)
  view.setUint32(20, height)
  return PNG_PREFIX + btoa(String.fromCharCode(...bytes))
}
it('accepts bounded embedded PNG headers and rejects paths, SVG, invalid base64 and oversized dimensions', () => {
  expect(graphicDimensions(pngHeader(10, 20))).toEqual({ width: 10, height: 20 })
  for (const data of [
    'file:///etc/passwd',
    'https://example.com/image.png',
    'data:image/svg+xml,<svg/>',
    PNG_PREFIX + '!!!!',
    pngHeader(1025, 1),
    pngHeader(1, 0),
  ])
    expect(graphicDimensions(data)).toBeUndefined()
})
it('round-trips graphic properties without requiring PLC write permissions', () => {
  const screen = newScreen('s', 'Main'),
    element = newElement('graphic', 'g')
  screen.elements = [element]
  const doc = { ...emptyVisualization(), startScreen: 's', screens: [screen] }
  expect(() => exportVisualization(doc, [])).toThrow('image is missing')
  element.graphic = { data: pngHeader(10, 20), fit: 'cover' }
  expect(TargetVisuSchema.parse(JSON.parse(exportVisualization(doc, [])))).toEqual(doc)
})
