<?php
// Alarm harga per akun: GET daftar, POST {add:{m,t,op,p}} | {del:id} | {unlink:1}. Dicek saat data diperbarui (alarm_check.php).
require __DIR__ . '/lib.php';
$u = session_user();
if (!$u) json_out(['ok' => false, 'msg' => 'Sesi habis. Masuk lagi.'], 401);
$code = $u['code'];
$view = function (array $db) use ($code) {
    $bot = $db['bot'] ?? '';
    return ['ok' => true, 'alarms' => array_values($db['alarms'][$code] ?? []), 'fired' => array_slice($db['afired'][$code] ?? [], -10),
        'linked' => !empty($db['codes'][$code]['tg']), 'link' => $bot ? "https://t.me/$bot?start=" . link_tok($code) : null, 'max' => CF_ALARM_MAX];
};
if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    [$fh, $db] = db_open();
    if (empty($db['bot'])) { $r = tg('getMe', []); if (!empty($r['result']['username'])) $db['bot'] = $r['result']['username']; }
    db_save($fh, $db);
    json_out($view($db));
}
if (!same_origin()) json_out(['ok' => false, 'msg' => 'Permintaan tidak sah.'], 400);
$in = body();
[$fh, $db] = db_open();
$list = $db['alarms'][$code] ?? [];
if (!empty($in['add']) && is_array($in['add'])) {
    $a = $in['add'];
    $m = ($a['m'] ?? '') === 'us' ? 'us' : 'id';
    $t = strtoupper(trim((string)($a['t'] ?? '')));
    $op = ($a['op'] ?? '') === 'ge' ? 'ge' : 'le';
    $p = (float)($a['p'] ?? 0);
    if (!preg_match('/^[A-Z0-9.\-]{1,12}$/', $t) || !($p > 0) || $p > 1e9) { db_close($fh); json_out(['ok' => false, 'msg' => 'Isi kode saham dan harga dengan benar.'], 400); }
    if (count($list) >= CF_ALARM_MAX) { db_close($fh); json_out(['ok' => false, 'msg' => 'Maksimal ' . CF_ALARM_MAX . ' alarm aktif. Hapus yang lama dulu.'], 400); }
    foreach ($list as $x) if ($x['m'] === $m && $x['t'] === $t && $x['op'] === $op && abs($x['p'] - $p) < 1e-9) { db_close($fh); json_out(['ok' => false, 'msg' => 'Alarm yang sama sudah ada.'], 400); }
    $list[] = ['id' => rnd(4), 'm' => $m, 't' => $t, 'op' => $op, 'p' => $p, 'note' => mb_substr((string)($a['note'] ?? ''), 0, 60), 'c' => now()];
} elseif (!empty($in['del'])) {
    $list = array_values(array_filter($list, function ($x) use ($in) { return $x['id'] !== (string)$in['del']; }));
} elseif (!empty($in['unlink'])) {
    unset($db['codes'][$code]['tg']);
}
if ($list) $db['alarms'][$code] = $list; else unset($db['alarms'][$code]);
db_save($fh, $db);
json_out($view($db));
