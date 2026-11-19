/** Build the two apps' web assets from generated originals. Run after npm ci in storefront. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(path.join(root,'storefront/package.json'));
const sharp=require('sharp');
const catalog=JSON.parse(await fs.readFile(path.join(root,'data/menu/catalog.json'),'utf8'));
const sources=[];
for(const item of catalog.items){
 const candidates=[path.join(root,'frontend/public/menu',item.slug+'.png'),path.join(root,'.local/menu-source',item.slug+'.png')];
 let source;
 for(const candidate of candidates){try{await fs.access(candidate);source=candidate;break;}catch{}}
 if(!source)throw new Error('Missing original: '+item.slug);
 sources.push([item,source]);
}
for(const dir of ['frontend/public/menu-images','storefront/public/menu-images','.local/menu-source'])await fs.mkdir(path.join(root,dir),{recursive:true});
const manifest=[];
for(const [item,source] of sources){
 const image=await sharp(source).resize(960,640,{fit:'cover'}).webp({quality:82,effort:4}).toBuffer();
 for(const dir of ['frontend/public/menu-images','storefront/public/menu-images'])await fs.writeFile(path.join(root,dir,item.slug+'.webp'),image);
 const archived=path.join(root,'.local/menu-source',item.slug+'.png');
 if(source!==archived)await fs.rename(source,archived);
 manifest.push({slug:item.slug,url:'/menu-images/'+item.slug+'.webp',width:960,height:640,bytes:image.length});
}
await fs.writeFile(path.join(root,'data/menu/images.json'),JSON.stringify({kind:'generated_menu_photography',images:manifest},null,2)+'\n');
console.log(`${manifest.length} images; ${(manifest.reduce((n,i)=>n+i.bytes,0)/1024/1024).toFixed(2)} MiB per app`);
