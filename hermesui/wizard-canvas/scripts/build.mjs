import { cp, mkdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const publicDir = path.join(root, '.build-public');
const outputDir = path.resolve(root, '../../static/wizard-canvas');
const packageRoot = path.join(root, 'node_modules/@excalidraw/excalidraw');

await rm(publicDir, { recursive: true, force: true });
await mkdir(publicDir, { recursive: true });
await cp(path.join(packageRoot, 'dist/prod/fonts'), path.join(publicDir, 'fonts'), { recursive: true });
await writeFile(
  path.join(publicDir, 'asset-path.js'),
  `window.EXCALIDRAW_ASSET_PATH = new URL("./fonts/", window.location.href).href;\nwindow.EXCALIDRAW_EXPORT_SOURCE = window.location.origin + "/hermesUI/";\n`,
  'utf8',
);

await new Promise((resolve, reject) => {
  const child = spawn(path.join(root, 'node_modules/.bin/vite'), ['build'], {
    cwd: root,
    stdio: 'inherit',
  });
  child.once('error', reject);
  child.once('exit', code => code === 0 ? resolve() : reject(new Error(`Vite build exited ${code}`)));
});

await cp(
  path.join(root, 'LICENSE.excalidraw.txt'),
  path.join(outputDir, 'EXCALIDRAW_LICENSE.txt'),
);
