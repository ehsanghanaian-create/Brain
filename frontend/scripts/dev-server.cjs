// Launcher used by .claude/launch.json: Next.js must run with cwd = project root (it resolves paths relative to cwd).
const path = require('path');
process.chdir(path.resolve(__dirname, '..'));
const port = process.env.PORT || '3000';
process.argv = [process.argv[0], require.resolve('next/dist/bin/next'), 'dev', '-p', port, '-H', '127.0.0.1'];
require('next/dist/bin/next');
