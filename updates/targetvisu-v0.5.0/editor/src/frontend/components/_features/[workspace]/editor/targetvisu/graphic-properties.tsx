// SPDX-License-Identifier: GPL-3.0-only
import { useEffect, useRef, useState } from 'react'
import type { VisuElement } from '../../../../../../middleware/shared/targetvisu/model'
import { graphicDimensions, MAX_GRAPHIC_SIDE } from '../../../../../../middleware/shared/targetvisu/graphics'

type Graphic = NonNullable<VisuElement['graphic']>

export async function importGraphic(file: File): Promise<string> {
  if (!/\.(png|jpe?g)$/i.test(file.name) || file.size > 8 * 1024 * 1024)
    throw new Error('Выберите PNG или JPEG размером не более 8 МиБ.')
  const header = new Uint8Array(await file.slice(0, 8).arrayBuffer())
  const png = [137, 80, 78, 71, 13, 10, 26, 10].every((byte, i) => header[i] === byte)
  const jpeg = header[0] === 255 && header[1] === 216 && header[2] === 255
  if (!png && !jpeg) throw new Error('Файл не является PNG или JPEG.')
  const url = URL.createObjectURL(file)
  try {
    const image = new Image()
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('Не удалось прочитать изображение.'))
      image.src = url
    })
    if (!image.naturalWidth || !image.naturalHeight) throw new Error('Изображение пустое.')
    const scale = Math.min(1, MAX_GRAPHIC_SIDE / Math.max(image.naturalWidth, image.naturalHeight))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Не удалось подготовить изображение.')
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    const data = canvas.toDataURL('image/png')
    if (!graphicDimensions(data)) throw new Error('PNG после обработки превышает 1 МиБ. Уменьшите изображение.')
    return data
  } finally {
    URL.revokeObjectURL(url)
  }
}

export function GraphicProperties({
  element,
  onChange,
}: {
  element: VisuElement
  onChange: (graphic: Graphic) => void
}) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const pending = useRef(0)
  const latest = useRef({ element, onChange })
  latest.current = { element, onChange }
  useEffect(
    () => () => {
      pending.current++
    },
    [],
  )
  return (
    <div className='flex flex-col gap-2'>
      <label>
        Изображение PNG / JPEG
        <input
          aria-label='Graphic file'
          type='file'
          accept='.png,.jpg,.jpeg,image/png,image/jpeg'
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0]
            event.target.value = ''
            if (!file) return
            const request = ++pending.current
            setBusy(true)
            setError('')
            void importGraphic(file)
              .then((data) => {
                if (request === pending.current)
                  latest.current.onChange({ data, fit: latest.current.element.graphic?.fit ?? 'contain' })
              })
              .catch((e: unknown) => {
                if (request === pending.current) setError(e instanceof Error ? e.message : String(e))
              })
              .finally(() => {
                if (request === pending.current) setBusy(false)
              })
          }}
        />
      </label>
      <label>
        Масштабирование
        <select
          aria-label='Graphic fit'
          value={element.graphic?.fit ?? 'contain'}
          onChange={(e) => onChange({ data: element.graphic?.data ?? '', fit: e.target.value as Graphic['fit'] })}
        >
          <option value='contain'>Вписать с сохранением пропорций</option>
          <option value='cover'>Заполнить с обрезкой</option>
          <option value='stretch'>Растянуть</option>
        </select>
      </label>
      <span className='text-xs'>Встраивается в проект; до 1024 × 1024 пикселей и 1 МиБ PNG.</span>
      {busy && <span>Загрузка…</span>}
      {error && <span role='alert'>{error}</span>}
    </div>
  )
}
