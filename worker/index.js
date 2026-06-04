/**
 * Cloudflare Email Worker — grocery@myblumberg.com
 *
 * Receives inbound email via Cloudflare Email Routing, extracts sender + body,
 * and forwards to the FastAPI backend for categorization.
 *
 * Deployment:
 *   wrangler deploy
 *
 * Required Worker secrets (set in Cloudflare dashboard, NOT in code):
 *   WORKER_SECRET  — must match the value in .env on the droplet
 *
 * Manual setup required before this Worker will receive email:
 *   1. Create grocery@myblumberg.com in Hosted Exchange
 *   2. Configure Cloudflare Email Routing to route that address to this Worker
 *   3. Set up forwarding in Exchange to the Cloudflare inbound address
 */

export default {
  async email(message, env, ctx) {
    const sender = message.from;
    const subject = message.headers.get('subject') || '';
    const body = await readEmailBody(message);

    const response = await fetch('https://tools.myblumberg.com/grocery/api/inbound-email', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Worker-Secret': env.WORKER_SECRET,
      },
      body: JSON.stringify({ sender, subject, body }),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Backend returned ${response.status}: ${text}`);
    }
  },
};

async function readEmailBody(message) {
  // Cloudflare provides a ReadableStream on message.raw
  // We read it and extract the plain-text body.
  const raw = await streamToText(message.raw);
  return extractTextBody(raw);
}

async function streamToText(stream) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let result = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    result += decoder.decode(value, { stream: true });
  }
  result += decoder.decode();
  return result;
}

function extractTextBody(raw) {
  // For plain-text emails, the body follows the headers (separated by \r\n\r\n or \n\n).
  // For multipart emails, grab the first text/plain part.
  const headerBodySplit = raw.indexOf('\r\n\r\n') !== -1
    ? raw.indexOf('\r\n\r\n')
    : raw.indexOf('\n\n');

  if (headerBodySplit === -1) return raw;

  const headers = raw.slice(0, headerBodySplit).toLowerCase();
  const body = raw.slice(headerBodySplit + (raw.indexOf('\r\n\r\n') !== -1 ? 4 : 2));

  // Multipart: find text/plain boundary
  const ctMatch = headers.match(/content-type:\s*multipart\/[^;]+;\s*boundary="?([^"\r\n]+)"?/);
  if (ctMatch) {
    const boundary = ctMatch[1].trim();
    const parts = body.split('--' + boundary);
    for (const part of parts) {
      if (part.toLowerCase().includes('content-type: text/plain')) {
        const partBodyIdx = part.indexOf('\r\n\r\n') !== -1 ? part.indexOf('\r\n\r\n') : part.indexOf('\n\n');
        if (partBodyIdx !== -1) {
          return part.slice(partBodyIdx + 4).replace(/--$/, '').trim();
        }
      }
    }
  }

  return body.trim();
}
