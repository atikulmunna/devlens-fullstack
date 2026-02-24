const test = require('node:test');
const assert = require('node:assert/strict');

process.env.NEXT_PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const { renderRoute } = require('./server');

test('analyze route renders actionable controls', () => {
  const html = renderRoute('/analyze');
  assert.ok(html.includes('id="submit-btn"'));
  assert.ok(html.includes('id="copy-repo-id"'));
  assert.ok(html.includes('id="copy-dashboard-url"'));
  assert.ok(html.includes('window.__devlensRunAnalyze = runAnalyze;'));
});

test('analyze route script keeps escaped newline split', () => {
  const html = renderRoute('/analyze');
  assert.ok(html.includes("const lines = text.split('\\n');"));
});

test('unknown route returns null', () => {
  const html = renderRoute('/does-not-exist');
  assert.equal(html, null);
});
