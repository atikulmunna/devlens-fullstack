function required(name) {
  const value = process.env[name];
  if (!value || value.trim() === '') {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function parsePort(value) {
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`Invalid PORT value: ${value}`);
  }
  return port;
}

function validateUrl(name, value) {
  try {
    new URL(value);
    return value;
  } catch {
    throw new Error(`Invalid URL for ${name}: ${value}`);
  }
}

function loadConfig() {
  return {
    apiUrl: validateUrl('NEXT_PUBLIC_API_URL', required('NEXT_PUBLIC_API_URL')),
    port: parsePort(process.env.PORT || '3000'),
    env: process.env.NODE_ENV || 'development',
  };
}

module.exports = { loadConfig };
