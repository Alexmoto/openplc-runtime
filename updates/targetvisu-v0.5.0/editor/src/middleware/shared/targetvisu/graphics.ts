// SPDX-License-Identifier: GPL-3.0-only
export const MAX_GRAPHIC_BYTES = 1024 * 1024
export const MAX_GRAPHIC_SIDE = 1024
export const PNG_PREFIX = 'data:image/png;base64,'

/** Only self-contained, bounded PNGs are accepted by both Editor and Runtime. */
export function graphicDimensions(data: string): { width: number; height: number } | undefined {
  if (!data.startsWith(PNG_PREFIX) || data.length > PNG_PREFIX.length + 4 * Math.ceil(MAX_GRAPHIC_BYTES / 3)) return
  const encoded = data.slice(PNG_PREFIX.length)
  if (!encoded || encoded.length % 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)) return
  try {
    const raw = atob(encoded)
    if (
      raw.length < 33 ||
      raw.length > MAX_GRAPHIC_BYTES ||
      raw.slice(0, 8) !== '\x89PNG\r\n\x1a\n' ||
      raw.slice(8, 16) !== '\x00\x00\x00\rIHDR'
    )
      return
    const uint32 = (offset: number) => [0, 1, 2, 3].reduce((n, i) => n * 256 + raw.charCodeAt(offset + i), 0)
    const width = uint32(16),
      height = uint32(20)
    if (width < 1 || height < 1 || width > MAX_GRAPHIC_SIDE || height > MAX_GRAPHIC_SIDE) return
    return { width, height }
  } catch {
    return
  }
}
