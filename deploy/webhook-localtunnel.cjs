const localtunnel = require('localtunnel');

const subdomain = process.env.WEBHOOK_SUBDOMAIN;
if (!/^[a-z0-9][a-z0-9-]{2,62}$/.test(subdomain || '')) {
  throw new Error('Set WEBHOOK_SUBDOMAIN to a unique DNS label');
}

async function run() {
  for (;;) {
    let tunnel;
    try {
      tunnel = await localtunnel({port: 80, local_host: 'webhook-proxy', subdomain});
      // Занятое имя не должно незаметно заменяться случайным адресом.
      if (new URL(tunnel.url).hostname.split('.')[0] !== subdomain) {
        throw new Error('Requested subdomain is unavailable');
      }
      console.log(JSON.stringify({webhook_url: tunnel.url + '/api/payments/webhook'}));
      await new Promise((resolve, reject) => {
        tunnel.once('close', resolve);
        tunnel.once('error', reject);
      });
    } catch (error) {
      console.error('Webhook tunnel unavailable:', error.message);
    } finally {
      if (tunnel) tunnel.close();
    }
    await new Promise(resolve => setTimeout(resolve, 5000));
  }
}

run().catch(() => process.exit(1));
