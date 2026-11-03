import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { TargetVisuDesigner } from '../designer'
import {
  emptyVisualization,
  newElement,
  newScreen,
  type TargetVisuDocument,
} from '@root/middleware/shared/targetvisu/model'
const symbols = [
  { path: 'Pump.Run', type: 'BOOL', writable: true },
  { path: 'Pump.Pressure', type: 'REAL', writable: false },
]
function Harness({
  initial = emptyVisualization(),
  readOnly = false,
}: {
  initial?: TargetVisuDocument
  readOnly?: boolean
}) {
  const [doc, setDoc] = useState(initial)
  return (
    <>
      <TargetVisuDesigner document={doc} symbols={symbols} onChange={setDoc} readOnly={readOnly} />
      <output data-testid='document'>{JSON.stringify(doc)}</output>
    </>
  )
}
const doc = () => JSON.parse(screen.getByTestId('document').textContent!) as TargetVisuDocument
it('creates screens and all primitives and retains model edits through Undo/Redo', () => {
  render(<Harness />)
  fireEvent.click(screen.getByRole('button', { name: 'Create screen' }))
  for (const name of ['rectangle', 'ellipse', 'line', 'text', 'indicator', 'button', 'number'])
    fireEvent.click(screen.getByRole('button', { name: `+ ${name}` }))
  expect(doc().screens[0].elements).toHaveLength(7)
  fireEvent.change(screen.getByLabelText('Element name'), { target: { value: 'Setpoint' } })
  expect(doc().screens[0].elements[6].name).toBe('Setpoint')
  fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
  expect(doc().screens[0].elements[6].name).not.toBe('Setpoint')
  fireEvent.click(screen.getByRole('button', { name: 'Redo' }))
  expect(doc().screens[0].elements[6].name).toBe('Setpoint')
})
it('duplicates a selected element with a new identity and deletes without losing other elements', () => {
  render(<Harness />)
  fireEvent.click(screen.getByRole('button', { name: 'Create screen' }))
  fireEvent.click(screen.getByRole('button', { name: '+ rectangle' }))
  fireEvent.click(screen.getByRole('button', { name: 'Duplicate' }))
  const elements = doc().screens[0].elements
  expect(elements).toHaveLength(2)
  expect(elements[0].id).not.toBe(elements[1].id)
  fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
  expect(doc().screens[0].elements).toHaveLength(1)
})
it('checks missing variables and prevents exporting an unresolved screen', () => {
  const s = newScreen('s', 'Main'),
    e = newElement('text', 'e')
  e.bindings.value = 'Deleted.Value'
  s.elements = [e]
  render(<Harness initial={{ ...emptyVisualization(), screens: [s], startScreen: 's' }} />)
  expect(screen.getByRole('alert').textContent).toContain('unknown variable')
  fireEvent.click(screen.getByRole('button', { name: 'Export JSON' }))
  expect(screen.getByRole('alert').textContent).toContain('Deleted.Value')
})
it('preview changes local values without altering the project JSON', () => {
  const s = newScreen('s', 'Main'),
    e = newElement('button', 'e')
  e.action = { kind: 'toggle', target: 'Pump.Run', value: true }
  s.elements = [e]
  render(<Harness initial={{ ...emptyVisualization(), screens: [s], startScreen: 's' }} />)
  const initial = JSON.stringify(doc())
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
  expect(screen.getByText('No values are sent to the PLC.')).toBeTruthy()
  fireEvent.pointerDown(screen.getByTestId('element-e'))
  expect((screen.getByLabelText('Preview Pump.Run') as HTMLInputElement).checked).toBe(true)
  expect(JSON.stringify(doc())).toBe(initial)
})
it('prevents model edits in read-only projects', () => {
  render(<Harness readOnly />)
  expect((screen.getByRole('button', { name: 'Create screen' }) as HTMLButtonElement).disabled).toBe(true)
})

it('commits numeric dimensions on blur so typing does not clamp intermediate digits', () => {
  render(<Harness />)
  fireEvent.click(screen.getByRole('button', { name: 'Create screen' }))
  const width = screen.getByLabelText('Screen width')
  fireEvent.change(width, { target: { value: '320' } })
  expect(doc().screens[0].width).toBe(800)
  fireEvent.blur(width)
  expect(doc().screens[0].width).toBe(320)
})
it('releases a simulated momentary button on pointer cancel', () => {
  const s = newScreen('s', 'Main'),
    e = newElement('button', 'momentary')
  e.action = { kind: 'momentary', target: 'Pump.Run', value: true }
  s.elements = [e]
  render(<Harness initial={{ ...emptyVisualization(), screens: [s], startScreen: 's' }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
  fireEvent.pointerDown(screen.getByTestId('element-momentary'))
  expect((screen.getByLabelText('Preview Pump.Run') as HTMLInputElement).checked).toBe(true)
  fireEvent.pointerCancel(screen.getByTestId('element-momentary'))
  expect((screen.getByLabelText('Preview Pump.Run') as HTMLInputElement).checked).toBe(false)
})

it('resets a momentary preview with a case-insensitive variable path when leaving preview', () => {
  const s = newScreen('s', 'Main'),
    e = newElement('button', 'm')
  e.action = { kind: 'momentary', target: 'PUMP.RUN', value: true }
  s.elements = [e]
  render(<Harness initial={{ ...emptyVisualization(), screens: [s], startScreen: 's' }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
  fireEvent.pointerDown(screen.getByTestId('element-m'))
  expect((screen.getByLabelText('Preview Pump.Run') as HTMLInputElement).checked).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Design' }))
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
  expect((screen.getByLabelText('Preview Pump.Run') as HTMLInputElement).checked).toBe(false)
})

it('configures navigation by screen id and previews a button transition without modifying the document', () => {
  const main = newScreen('main', 'Main'),
    details = newScreen('details', 'Details')
  render(<Harness initial={{ ...emptyVisualization(), screens: [main, details], startScreen: main.id }} />)
  fireEvent.click(screen.getByRole('button', { name: '+ button' }))
  fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'navigate' } })
  expect((screen.getByLabelText('Target screen') as HTMLSelectElement).value).toBe('details')
  expect(screen.queryByLabelText('Action target')).toBeNull()
  const button = doc().screens[0].elements[0]
  expect(button.action).toMatchObject({ kind: 'navigate', target: 'details' })
  const original = JSON.stringify(doc())
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
  fireEvent.pointerDown(screen.getByTestId(`element-${button.id}`))
  expect(screen.queryByTestId(`element-${button.id}`)).toBeNull()
  expect(JSON.stringify(doc())).toBe(original)
})
