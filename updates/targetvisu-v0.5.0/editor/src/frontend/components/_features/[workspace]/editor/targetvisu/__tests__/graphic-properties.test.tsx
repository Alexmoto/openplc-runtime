import { importGraphic } from '../graphic-properties'

const header = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])
const file = (name = 'image.png', bytes = header) =>
  ({ name, size: bytes.length, slice: () => ({ arrayBuffer: async () => bytes.buffer }) }) as unknown as File

it('rejects unsupported formats and disguised SVG before decoding', async () => {
  await expect(importGraphic(file('image.svg'))).rejects.toThrow('PNG или JPEG')
  await expect(importGraphic(file('image.png', new Uint8Array([60, 115, 118, 103])))).rejects.toThrow('не является')
})
it('rejects files above the input limit before allocating a preview', async () => {
  await expect(importGraphic({ name: 'large.png', size: 9 * 1024 * 1024 } as File)).rejects.toThrow('8 МиБ')
})
