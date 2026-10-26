<?php
// ChartFlow: pustaka bersama (kode akses, sesi, Telegram). PHP 7.4+.
declare(strict_types=1);
require __DIR__ . '/../_data/config.php'; // dibuat otomatis saat deploy: CF_BOT_TOKEN, CF_CHAT_ID, CF_HOOK_SECRET, CF_SALT

const CF_DB = __DIR__ . '/../_data/db.json';
const CF_DAYS = 30;          // masa berlaku kode bawaan
const CF_DEVICES = 2;        // perangkat per kode
const CF_COOKIE = 'cf_sess';

function db_open(): array {
    $fh = fopen(CF_DB, 'c+');
    flock($fh, LOCK_EX);
    $raw = stream_get_contents($fh);
    $db = $raw ? json_decode($raw, true) : null;
    if (!is_array($db)) $db = ['codes' => [], 'sessions' => [], 'reqs' => [], 'rate' => []];
    return [$fh, $db];
}
function db_save($fh, array $db): void {
    ftruncate($fh, 0); rewind($fh);
    fwrite($fh, json_encode($db, JSON_UNESCAPED_UNICODE));
    fflush($fh); flock($fh, LOCK_UN); fclose($fh);
}
function db_close($fh): void { flock($fh, LOCK_UN); fclose($fh); }

function now(): int { return time(); }
function user_file(string $code): string { return __DIR__ . '/../_data/users/' . substr(hash('sha256', $code . CF_SALT), 0, 32) . '.json'; }
function ip_key(): string { return substr(hash('sha256', ($_SERVER['REMOTE_ADDR'] ?? '') . CF_SALT), 0, 16); }
function rnd(int $n): string { return bin2hex(random_bytes($n)); }
function new_code(): string {
    $a = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'; $s = '';
    for ($i = 0; $i < 8; $i++) $s .= $a[random_int(0, strlen($a) - 1)];
    return 'CF-' . substr($s, 0, 4) . '-' . substr($s, 4);
}
function norm_code(string $c): string {
    $c = strtoupper(preg_replace('/[^A-Za-z0-9]/', '', $c));
    if (strpos($c, 'CF') === 0) $c = substr($c, 2);
    return strlen($c) === 8 ? 'CF-' . substr($c, 0, 4) . '-' . substr($c, 4) : '';
}
function fmt_date(int $t): string {
    $b = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];
    $d = new DateTime('@' . $t); $d->setTimezone(new DateTimeZone('Asia/Jakarta'));
    return $d->format('j') . ' ' . $b[(int)$d->format('n') - 1] . ' ' . $d->format('Y');
}

/** Batasi percobaan: $max kali per $win detik per IP untuk aksi $k. */
function rate_ok(array &$db, string $k, int $max, int $win): bool {
    $key = $k . ':' . ip_key(); $t = now();
    $hits = array_values(array_filter($db['rate'][$key] ?? [], function ($x) use ($t, $win) { return $x > $t - $win; }));
    if (count($hits) >= $max) { $db['rate'][$key] = $hits; return false; }
    $hits[] = $t; $db['rate'][$key] = $hits;
    return true;
}
// cek batas tanpa menambah hitungan; kembalikan detik tunggu (0 = boleh)
function rate_wait(array &$db, string $k, int $max, int $win): int {
    $key = $k . ':' . ip_key(); $t = now();
    $hits = array_values(array_filter($db['rate'][$key] ?? [], function ($x) use ($t, $win) { return $x > $t - $win; }));
    $db['rate'][$key] = $hits;
    return count($hits) >= $max ? max(1, min($hits) + $win - $t) : 0;
}
function rate_hit(array &$db, string $k): void { $db['rate'][$k . ':' . ip_key()][] = now(); }
function prune(array &$db): void {
    $t = now();
    foreach ($db['rate'] as $k => $v) { $v = array_filter($v, function ($x) use ($t) { return $x > $t - 86400; }); if (!$v) unset($db['rate'][$k]); else $db['rate'][$k] = array_values($v); }
    foreach ($db['sessions'] as $tok => $s) { $c = $db['codes'][$s['code']] ?? null; if (!$c || $c['status'] !== 'active' || $c['exp'] < $t) unset($db['sessions'][$tok]); }
    foreach ($db['reqs'] as $id => $r) { if ($r['t'] < $t - 30 * 86400) unset($db['reqs'][$id]); }
    // kode dicabut/habis lebih dari 90 hari: hapus beserta data akunnya
    foreach ($db['codes'] as $c => $v) {
        $end = $v['status'] === 'revoked' ? ($v['revoked'] ?? $v['exp']) : $v['exp'];
        if ($end < $t - 90 * 86400) { @unlink(user_file($c)); unset($db['codes'][$c]); }
    }
}

/** Sesi yang sah dari cookie, atau null. */
function session_user(): ?array {
    $tok = $_COOKIE[CF_COOKIE] ?? '';
    if (!preg_match('/^[a-f0-9]{64}$/', $tok)) return null;
    $fh = fopen(CF_DB, 'r'); if (!$fh) return null;
    flock($fh, LOCK_SH); $db = json_decode((string)stream_get_contents($fh), true); flock($fh, LOCK_UN); fclose($fh);
    $s = $db['sessions'][hash('sha256', $tok)] ?? null; if (!$s) return null;
    $c = $db['codes'][$s['code']] ?? null;
    if (!$c || $c['status'] !== 'active' || $c['exp'] < now()) return null;
    return ['code' => $s['code'], 'name' => $c['name'] ?? '', 'exp' => $c['exp'], 'sid' => hash('sha256', $tok)];
}

function json_out(array $a, int $code = 200): void {
    http_response_code($code); header('Content-Type: application/json; charset=utf-8'); header('Cache-Control: no-store');
    echo json_encode($a, JSON_UNESCAPED_UNICODE); exit;
}
function same_origin(): bool {
    $o = $_SERVER['HTTP_ORIGIN'] ?? ''; $h = $_SERVER['HTTP_HOST'] ?? '';
    if ($o === '') return true;
    $u = parse_url($o);
    $oh = ($u['host'] ?? '') . (isset($u['port']) ? ':' . $u['port'] : '');
    return strcasecmp($oh, $h) === 0;
}
function body(): array { $j = json_decode((string)file_get_contents('php://input'), true); return is_array($j) ? $j : $_POST; }

function tg(string $method, array $params): ?array {
    $ch = curl_init('https://api.telegram.org/bot' . CF_BOT_TOKEN . '/' . $method);
    curl_setopt_array($ch, [CURLOPT_POST => true, CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 15,
        CURLOPT_HTTPHEADER => ['Content-Type: application/json'], CURLOPT_POSTFIELDS => json_encode($params)]);
    $r = curl_exec($ch); curl_close($ch);
    return $r ? json_decode($r, true) : null;
}
function link_tok(string $code): string { return substr(hash_hmac('sha256', $code, CF_SALT . ':tglink'), 0, 24); }
function money_fmt(float $v, string $m): string { return $m === 'id' ? 'Rp' . number_format($v, 0, ',', '.') : '$' . number_format($v, 2, ',', '.'); }
const CF_ALARM_MAX = 30;
function h(string $s): string { return htmlspecialchars($s, ENT_QUOTES, 'UTF-8'); }
