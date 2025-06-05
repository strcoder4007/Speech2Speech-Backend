const https = require('https');
const httpProxy = require('http-proxy');
const fs = require('fs');

// Create proxy server to forward to your app
const proxy = httpProxy.createProxyServer({ target: 'http://127.0.0.1:8001' });

const server = https.createServer({
  key: fs.readFileSync('../ssl/key.pem'),
  cert: fs.readFileSync('../ssl/cert.pem')
}, (req, res) => {
  proxy.web(req, res);
});

server.listen(3443, () => {
  console.log('🔐 HTTPS Proxy running on https://0.0.0.0:3443');
});
