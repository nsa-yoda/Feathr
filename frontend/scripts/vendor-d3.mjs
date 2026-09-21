import { copyFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';

const source = resolve('node_modules/d3/dist/d3.min.js');
const target = resolve('public/vendor/d3.min.js');
await mkdir(dirname(target), { recursive: true });
await copyFile(source, target);
console.log(`vendored D3 from ${source} to ${target}`);
