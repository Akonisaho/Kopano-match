import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './auth'
import { LangProvider } from './i18n'
import './index.css'
import { ToastProvider } from './ui'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <LangProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </LangProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
