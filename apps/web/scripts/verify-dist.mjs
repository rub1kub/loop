import { readFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const distRoot = fileURLToPath(new URL('../dist/', import.meta.url));
const assetsRoot = fileURLToPath(new URL('../dist/assets/', import.meta.url));
const indexHtml = await readFile(new URL('../dist/index.html', import.meta.url), 'utf8');
const entryMatch = indexHtml.match(/<script[^>]+src="\/(assets\/[^"]+\.js)"/);

if (!entryMatch) {
  throw new Error('Production index does not reference a JavaScript entry');
}

const entrySource = await readFile(new URL(`../dist/${entryMatch[1]}`, import.meta.url), 'utf8');
const assetNames = await readdir(assetsRoot);
const stylesheets = assetNames.filter((name) => name.endsWith('.css')).sort();

if (stylesheets.length !== 3) {
  throw new Error(`Expected three surface stylesheets, found ${stylesheets.length}`);
}

for (const stylesheet of stylesheets) {
  if (!entrySource.includes(`assets/${stylesheet}`)) {
    throw new Error(`Production entry does not reference ${stylesheet}`);
  }
}

const referencedAssets = new Set(entrySource.match(/assets\/[A-Za-z0-9._-]+\.(?:css|js)/g) ?? []);
for (const asset of referencedAssets) {
  await readFile(new URL(`../dist/${asset}`, import.meta.url));
}

console.log(
  `Verified ${fileURLToPath(new URL('../dist/index.html', import.meta.url)).replace(`${distRoot}/`, '')}: ` +
    `${stylesheets.length} surface stylesheets and ${referencedAssets.size} direct assets`,
);
