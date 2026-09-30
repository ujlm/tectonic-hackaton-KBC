// Generates the demo voice-over with ElevenLabs text-to-speech.
// Usage:  ELEVENLABS_API_KEY=... node voice/generate.js
// Optional: ELEVENLABS_VOICE_ID (default: a premade voice), ELEVENLABS_MODEL (default: eleven_multilingual_v2)
// Output: voice/out/<segment>.mp3 and voice/out/voiceover-full.mp3. The key is read from the environment, never committed.

const fs = require('fs');
const path = require('path');

const KEY = process.env.ELEVENLABS_API_KEY;
const VOICE = process.env.ELEVENLABS_VOICE_ID || '21m00Tcm4TlvDq8ikWAM';
const MODEL = process.env.ELEVENLABS_MODEL || 'eleven_multilingual_v2';
if (!KEY) { console.error('Set ELEVENLABS_API_KEY first (see .env.example).'); process.exit(1); }

const { segments } = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'docs', 'voiceover.json'), 'utf8'));
const outDir = path.join(__dirname, 'out');
fs.mkdirSync(outDir, { recursive: true });

(async () => {
  const parts = [];
  for (const s of segments) {
    process.stdout.write(`→ ${s.id} ... `);
    const res = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${VOICE}`, {
      method: 'POST',
      headers: { 'xi-api-key': KEY, 'Content-Type': 'application/json', Accept: 'audio/mpeg' },
      body: JSON.stringify({ text: s.text, model_id: MODEL, voice_settings: { stability: 0.5, similarity_boost: 0.75 } })
    });
    if (!res.ok) { console.error(`failed (${res.status}): ${await res.text()}`); process.exit(1); }
    const buf = Buffer.from(await res.arrayBuffer());
    fs.writeFileSync(path.join(outDir, `${s.id}.mp3`), buf);
    parts.push(buf);
    console.log(`${Math.round(buf.length / 1024)} KB`);
  }
  // Simple byte concatenation plays fine in browsers and most editors.
  // For a clean file: ffmpeg -f concat -safe 0 -i list.txt -c copy voiceover-full.mp3
  fs.writeFileSync(path.join(outDir, 'voiceover-full.mp3'), Buffer.concat(parts));
  console.log(`\nDone: voice/out/voiceover-full.mp3 (${segments.length} segments)`);
})();
