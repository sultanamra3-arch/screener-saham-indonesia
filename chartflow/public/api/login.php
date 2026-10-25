<?php
// Masuk dengan kode akses -> cookie sesi (maks. CF_DEVICES perangkat per kode).
require __DIR__ . '/lib.php';
if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !same_origin()) json_out(['ok' => false, 'msg' => 'Permintaan tidak sah.'], 400);
$code = norm_code((string)(body()['code'] ?? ''));
[$fh, $db] = db_open();
if (!rate_ok($db, 'login', 8, 900)) { db_save($fh, $db); json_out(['ok' => false, 'msg' => 'Terlalu banyak percobaan. Tunggu 15 menit.'], 429); }
$c = $code ? ($db['codes'][$code] ?? null) : null;
if (!$c || $c['status'] !== 'active') { db_save($fh, $db); json_out(['ok' => false, 'msg' => 'Kode tidak dikenal atau sudah dicabut.'], 401); }
if ($c['exp'] < now()) { db_save($fh, $db); json_out(['ok' => false, 'msg' => 'Kode sudah habis masa berlakunya (' . fmt_date($c['exp']) . '). Minta perpanjangan ke pengelola.'], 401); }
prune($db);
$mine = array_filter($db['sessions'], function ($s) use ($code) { return $s['code'] === $code; });
if (count($mine) >= ($c['devices'] ?? CF_DEVICES)) { db_save($fh, $db); json_out(['ok' => false, 'msg' => 'Kode ini sudah dipakai di ' . count($mine) . ' perangkat. Hubungi pengelola untuk reset.'], 403); }
$tok = rnd(32);
$db['sessions'][hash('sha256', $tok)] = ['code' => $code, 't' => now(), 'ua' => mb_substr($_SERVER['HTTP_USER_AGENT'] ?? '', 0, 120)];
$db['codes'][$code]['last'] = now();
db_save($fh, $db);
setcookie(CF_COOKIE, $tok, ['expires' => $c['exp'], 'path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Lax']);
if (count($mine) === 0 && empty($c['notified'])) {
    tg('sendMessage', ['chat_id' => CF_CHAT_ID, 'parse_mode' => 'HTML', 'text' => '🔓 ' . h($c['name'] ?: $code) . ' masuk pertama kali (' . $code . ').']);
}
json_out(['ok' => true, 'name' => $c['name'] ?? '', 'exp' => fmt_date($c['exp'])]);
