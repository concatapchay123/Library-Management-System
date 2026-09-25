import { StrictMode } from 'react';
import ReactDOM from 'react-dom/client';
import App from './app/App';

const rootElement = document.getElementById('root');

const isDemo = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('demo') === '1';

if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <StrictMode>
      <App initialAuthenticated={isDemo} />
    </StrictMode>,
  );
}
