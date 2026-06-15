// Cloudflare Worker — Proxy لـ daleel API
// انشره على: dash.cloudflare.com → Workers & Pages → Create Worker

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, GET",
          "Access-Control-Allow-Headers": "Content-Type",
        },
      });
    }

    const url = new URL(request.url);
    const targetUrl = "https://daleel.mohaisentech.com" + url.pathname;

    const body = request.method === "POST" ? await request.arrayBuffer() : null;

    const resp = await fetch(targetUrl, {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
      },
      body: body,
    });

    const data = await resp.arrayBuffer();

    return new Response(data, {
      status: resp.status,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      },
    });
  },
};
