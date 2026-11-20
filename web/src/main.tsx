import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './app/App.tsx'
import { applyTheme, useUi } from './store/ui.ts'
import './styles.css'

const container = document.getElementById('root')
if (container === null) {
  throw new Error('Missing #root element in index.html')
}

applyTheme(useUi.getState().theme)

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
