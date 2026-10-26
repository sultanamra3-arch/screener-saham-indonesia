<?php
// Masuk dengan kode akses -> cookie sesi (maks. CF_DEVICES perangkat per kode).
// Perangkat penuh: pengguna boleh mengeluarkan perangkat lama sendiri 1x per 24 jam (pengelola diberi tahu).
require __DIR__ . '/lib.php';
if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !same_origin()) json_out(['ok' => false, 'msg' => 'Permintaan tidak sah.'], 400);
$in = body();
$code = norm_code((string)($in['code'] ?? ''));
$kick = !empty($in['kick']);
[$fh, $db] = db_open();
$jam = function (int $t): string { $d = new DateTime('@' . $t); $d->setTimezone(new DateTimeZone('Asia/Jakarta')); return $d->format('H.i') . ' WIB'; };
$wait = rate_wait($db, 'login', 8, 900);
if ($wait) { db_save($fh, $db); json_out(['ok' => false, 'msg' => 'Terlalu banyak kode salah. Coba lagi pukul ' . $jam(now() + $wait) . ' (sekitar ' . max(1, (int)ceil($wait / 60)) . ' menit lagi).'], 429); }
$c = $code ? ($db['codes'][$code] ?? null) : null;
if (!$c || $c['status'] !== 'active') { rate_hit($db, 'login'); db_save($fh, $db); json_out(['ok' => false, 'msg' => 'Kode tidak dikenal atau sudah dicabut.'], 401); }
if ($c['exp'] < now()) { db_save($fh, $db); json_out(['ok' => false, 'msg' => 'Kode sudah habis masa berlakunya (' . fmt_date($c['exp']) . '). Minta perpanjangan ke pengelola.'], 401); }
prune($db);
$mine = array_filter($db['sessions'], function ($s) use ($code) { return $s['code'] === $code; });
$max = $c['devices'] ?? CF_DEVICES;
$kicked = false;
if (count($mine) >= $max) {
    $next = (int)($c['sr'] ?? 0) + 86400;
    $can = $next <= now();
    if (!$kick) {
        db_save($fh, $db);
        json_out(['ok' => false, 'full' => true, 'canKick' => $can,
            'msg' => 'Kode ini sudah dipakai di ' . count($mine) . ' perangkat (batas ' . $max . ').' . ($can ? '' : ' Reset mandiri sudah dipakai; bisa lagi ' . fmt_date($next) . ' pukul ' . $jam($next) . ', atau hubungi pengelola.')], 403);
    }
    if (!$can) { db_save($fh, $db); json_out(['ok' => false, 'full' => true, 'canKick' => false, 'msg' => 'Reset mandiri hanya 1× per 24 jam. Bisa lagi ' . fmt_date($next) . ' pukul ' . $jam($next) . ', atau hubungi pengelola.'], 403); }
    // keluarkan perangkat yang paling lama tidak dipakai sampai tersisa satu slot
    uasort($mine, function ($a, $b) { return ($a['u'] ?? $a['t']) <=> ($b['u'] ?? $b['t']); });
    $n = count($mine) - $max + 1;
    foreach (array_keys($mine) as $sid) { if ($n-- <= 0) break; unset($db['sessions'][$sid]); }
    $db['codes'][$code]['sr'] = now();
    $kicked = true;
}
$tok = rnd(32);
$db['sessions'][hash('sha256', $tok)] = ['code' => $code, 't' => now(), 'u' => now(), 'ua' => mb_substr($_SERVER['HTTP_USER_AGENT'] ?? '', 0, 120)];
$db['codes'][$code]['last'] = now();
db_save($fh, $db);
setcookie(CF_COOKIE, $tok, ['expires' => $c['exp'], 'path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Lax']);
if ($kicked) {
    tg('sendMessage', ['chat_id' => CF_CHAT_ID, 'parse_mode' => 'HTML', 'text' => '♻️ ' . h($c['name'] ?: $code) . ' (<code>' . $code . '</code>) mengeluarkan perangkat lamanya sendiri lalu masuk di perangkat baru. Reset mandiri berikutnya bisa setelah 24 jam.']);
} elseif (count($mine) === 0 && empty($c['notified'])) {
    tg('sendMessage', ['chat_id' => CF_CHAT_ID, 'parse_mode' => 'HTML', 'text' => '🔓 ' . h($c['name'] ?: $code) . ' masuk pertama kali (' . $code . ').']);
}
json_out(['ok' => true, 'name' => $c['name'] ?? '', 'exp' => fmt_date($c['exp']), 'kicked' => $kicked]);
