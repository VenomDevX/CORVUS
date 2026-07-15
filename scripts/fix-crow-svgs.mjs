import fs from 'fs';
import path from 'path';

const dir = path.join(process.cwd(), 'public', 'crow_hovering');
const files = fs.readdirSync(dir);

for (const file of files) {
  if (file.endsWith('.svg')) {
    const p = path.join(dir, file);
    let content = fs.readFileSync(p, 'utf8');
    
    // Remove the outer bounding box path command
    const regex = /M0 3600 l0 -3600 6400 0 6400 0 0 3600 0 3600 -6400 0 -6400 0 0[\r\n\s]+-3600z\s+/;
    content = content.replace(regex, '');
    
    fs.writeFileSync(p, content);
  }
}
console.log('Finished processing SVGs.');
