import fs from 'fs';
import path from 'path';

const dir = path.join(process.cwd(), 'public', 'crow_hovering');
const files = fs.readdirSync(dir);

for (const file of files) {
  if (file.endsWith('.svg')) {
    const p = path.join(dir, file);
    let content = fs.readFileSync(p, 'utf8');
    
    // Fix the first path command
    content = content.replace(/d="m(\-?\d+)\s+(\-?\d+)/, (match, p1, p2) => {
        return `d="M${p1} ${Number(p2) + 3600}`;
    });
    
    fs.writeFileSync(p, content);
  }
}
console.log('Finished fixing SVG coordinates.');
