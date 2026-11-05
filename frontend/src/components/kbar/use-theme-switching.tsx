import { useRegisterActions } from 'kbar';
import { useTheme } from 'next-themes';

const useThemeSwitching = () => {
  const { resolvedTheme, setTheme } = useTheme();
  useRegisterActions(
    [
      {
        id: 'toggleDarkLight',
        name: 'تغییر حالت روشن و تاریک',
        shortcut: ['t', 't'],
        section: 'ظاهر پنل',
        perform: () => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')
      },
      {
        id: 'setLightTheme',
        name: 'حالت روشن',
        section: 'ظاهر پنل',
        perform: () => setTheme('light')
      },
      {
        id: 'setDarkTheme',
        name: 'حالت تاریک',
        section: 'ظاهر پنل',
        perform: () => setTheme('dark')
      }
    ],
    [resolvedTheme, setTheme]
  );
};
export default useThemeSwitching;
