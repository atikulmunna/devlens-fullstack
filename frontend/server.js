const http = require('http');

const port = Number(process.env.PORT || 3000);

const server = http.createServer((req, res) => {
  if (req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', service: 'frontend' }));
    return;
  }

  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('DevLens frontend scaffold is ready.');
});

server.listen(port, '0.0.0.0', () => {
  console.log(`Frontend listening on ${port}`);
});
