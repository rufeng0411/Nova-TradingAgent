import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import './styles/skins/tokens-default.css'
import './styles/workflow-n8n.css'
import { useThemeStore } from './stores/themeStore'
import { useWorkflowViewStore } from './stores/workflowViewStore'

useThemeStore.getState().hydrate()
useWorkflowViewStore.getState().hydrate()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
