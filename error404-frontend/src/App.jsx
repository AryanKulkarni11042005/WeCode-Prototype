import { BrowserRouter, Routes, Route } from 'react-router-dom';
import HomePage from './pages/HomePage';
import CompetitionPage from './pages/CompetitionPage';
import NewCompPage from './pages/NewCompPage';
import MatchPage from './pages/MatchPage';
import ReportsPage from './pages/ReportsPage';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/competition" element={<NewCompPage />} />
        <Route path="/match" element={<MatchPage />} />
        <Route path="/reports" element={<ReportsPage />} />
      </Routes>
    </BrowserRouter>
  );
}
