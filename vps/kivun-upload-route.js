
// ── POST /api/kivun/upload ────────────────────────────────────
// CI pushes each tagged Kivun installer here over HTTPS (the gov machine then
// pulls it over SSH — it can't reach GitHub). Auth: a DEDICATED bearer token
// (KIVUN_UPLOAD_TOKEN in .env), NOT the dashboard Basic creds (those also unlock
// run-backup/run-git). Writes, into the host-mounted kivun-updates/ dir,
// Setup-latest.exe (atomic) + latest.json {version,file,sha256}. Overwrite-latest
// = zero disk accumulation. Added after app.listen on purpose — Express matches
// routes per-request, so registration order vs listen() does not matter.
// Removal: delete this block + the KIVUN_UPLOAD_TOKEN line in .env.
const KIVUN_UPDATES_DIR = path.join(process.cwd(), 'kivun-updates');
const KIVUN_EXE_NAME = 'Setup-latest.exe';
const KIVUN_VERSION_RE = /^[0-9A-Za-z.\-]{1,32}$/;

app.post('/api/kivun/upload', (req, res) => {
  const token = process.env.KIVUN_UPLOAD_TOKEN || '';
  const auth = req.headers.authorization || '';
  const sent = auth.startsWith('Bearer ') ? auth.slice(7) : '';
  const a = Buffer.from(sent), b = Buffer.from(token);
  if (!token || a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
    return res.status(401).json({ message: 'unauthorized' });
  }

  const form = formidable({ maxFileSize: 200 * 1024 * 1024 });
  form.parse(req, async (err, fields, files) => {
    if (err) {
      console.error('kivun upload error:', err);
      return res.status(500).json({ message: 'upload failed', error: err.message });
    }
    const version = ((fields.version && fields.version[0]) || '').trim();
    if (!KIVUN_VERSION_RE.test(version)) {
      return res.status(400).json({ message: 'bad or missing version' });
    }
    if (!files.file || !files.file[0]) {
      return res.status(400).json({ message: 'missing file' });
    }
    try {
      await fs.ensureDir(KIVUN_UPDATES_DIR);
      const tmp = path.join(KIVUN_UPDATES_DIR, KIVUN_EXE_NAME + '.tmp');
      await fs.move(files.file[0].filepath, tmp, { overwrite: true });
      const sha = await new Promise((resolve, reject) => {
        const h = crypto.createHash('sha256');
        fs.createReadStream(tmp).on('data', d => h.update(d))
          .on('end', () => resolve(h.digest('hex')))
          .on('error', reject);
      });
      // atomic publish so a concurrent scp never sees a half-written exe
      const exePath = path.join(KIVUN_UPDATES_DIR, KIVUN_EXE_NAME);
      await fs.move(tmp, exePath, { overwrite: true });
      // size lets the app show a real download % over scp (it polls the partly
      // written file against this total — scp emits no parseable meter when piped).
      const size = (await fs.stat(exePath)).size;
      await fs.writeJson(path.join(KIVUN_UPDATES_DIR, 'latest.json'),
        { version, file: KIVUN_EXE_NAME, sha256: sha, size });
      console.log(`kivun upload ok: ${version} ${sha}`);
      res.status(200).json({ message: 'ok', version, sha256: sha });
    } catch (error) {
      console.error('kivun publish error:', error);
      res.status(500).json({ message: 'publish failed', error: error.message });
    }
  });
});
