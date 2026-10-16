import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const SignUtil = require('/home/hatch/workspace/daymatter-band8pro-work/daymatter-band8pro/node_modules/@aiot-toolkit/aiotpack/lib/compiler/javascript/vela/utils/signature/SignUtil.js').default;
const PEM_DIR = '/home/hatch/workspace/daymatter-band8pro-work/daymatter-band8pro/node_modules/@aiot-toolkit/aiotpack/lib/compiler/javascript/vela/utils/signature/pem';
const SRC = process.argv[2];
const OUT = process.argv[3];
function walk(dir, base, out) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    const rel = base ? base + '/' + name : name;
    if (fs.statSync(p).isDirectory()) walk(p, rel, out);
    else out.push({ fileBuildPath: rel, fileContentBuffer: fs.readFileSync(p) });
  }
  return out;
}
const resourceList = walk(SRC, '', []);
const target = {
  resourceList,
  comment: undefined,
  getResource(p) { return resourceList.find(i => i.fileBuildPath === p); },
};
const privatekey = fs.readFileSync(path.join(PEM_DIR, 'private.pem'));
const certificate = fs.readFileSync(path.join(PEM_DIR, 'certificate.pem'));
const signed = await SignUtil.signPackage(target, privatekey, certificate);
if (!signed) { console.error('SIGN FAILED'); process.exit(1); }
fs.writeFileSync(OUT, signed);
console.log('signed ->', OUT, signed.length, 'bytes,', resourceList.length, 'files');
