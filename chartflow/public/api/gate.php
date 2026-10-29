<?php
// Penjaga /app/: hanya pemilik sesi yang sah yang bisa membuka screener dan datanya.
require __DIR__ . '/lib.php';
$p = (string)($_GET['p'] ?? '');
$p = ltrim(str_replace(['\\', "\0"], '', $p), '/');
if ($p === '' ) $p = 'id/';
if (!preg_match('#^(id|us|kripto)(/.*)?$#', $p)) { http_response_code(404); exit; }
if (substr($p, -1) === '/' || preg_match('#^(id|us|kripto)$#', $p)) $p = rtrim($p, '/') . '/index.html';
$root = realpath(__DIR__ . '/../_appfiles');
$f = realpath($root . '/' . $p);
if (!$f || strpos($f, $root . DIRECTORY_SEPARATOR) !== 0 || !is_file($f)) { http_response_code(404); exit; }
$ext = strtolower(pathinfo($f, PATHINFO_EXTENSION));
$u = session_user();
if (!$u) {
    if ($ext === 'html') { header('Location: /?masuk=1&next=' . rawurlencode('/app/' . preg_replace('#index\.html$#', '', $p))); exit; }
    http_response_code(401); header('Content-Type: application/json'); echo '{"error":"login"}'; exit;
}
$types = ['html' => 'text/html; charset=utf-8', 'json' => 'application/json', 'js' => 'text/javascript; charset=utf-8', 'css' => 'text/css',
          'png' => 'image/png', 'svg' => 'image/svg+xml', 'webmanifest' => 'application/manifest+json', 'txt' => 'text/plain'];
header('Content-Type: ' . ($types[$ext] ?? 'application/octet-stream'));
header('Cache-Control: private, no-cache');
header('X-Content-Type-Options: nosniff');
$mt = filemtime($f); $etag = '"' . dechex($mt) . '-' . dechex(filesize($f)) . '"';
header('ETag: ' . $etag);
if (($_SERVER['HTTP_IF_NONE_MATCH'] ?? '') === $etag) { http_response_code(304); exit; }
if ($ext === 'js' && basename($f) === 'sw.js') header('Service-Worker-Allowed: /app/' . explode('/', $p)[0] . '/');
$gz = in_array($ext, ['json', 'html', 'js', 'css', 'svg'], true) && strpos($_SERVER['HTTP_ACCEPT_ENCODING'] ?? '', 'gzip') !== false && function_exists('gzencode');
if ($gz) { header('Content-Encoding: gzip'); header('Vary: Accept-Encoding'); echo gzencode((string)file_get_contents($f), 6); }
else { header('Content-Length: ' . filesize($f)); readfile($f); }
