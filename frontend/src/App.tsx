import { ThemeProvider } from './ThemeContext';
import Playground from './components/Playground';

export default function App() {
  return (
    <ThemeProvider>
      <Playground />
    </ThemeProvider>
  );
}
