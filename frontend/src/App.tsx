import { createBrowserRouter } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { Home } from './pages/Home';
import { Documents } from './pages/Documents';
import { Chat } from './pages/Chat';
import { Evaluation } from './pages/Evaluation';
import { Settings } from './pages/Settings';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Home /> },
      { path: 'documents', element: <Documents /> },
      { path: 'chat', element: <Chat /> },
      { path: 'evaluation', element: <Evaluation /> },
      { path: 'settings', element: <Settings /> },
      { path: '*', element: <Home /> },
    ],
  },
]);
