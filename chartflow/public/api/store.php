<?php
// Data akun (portofolio, saham ditandai, pengaturan kalkulator) per kode akses.
require __DIR__ . '/lib.php';
const CF_USER_MAX = 500000; // byte per akun
$u = session_user();
if (!$u) json_out(['ok' => false, 'msg' => 'login'], 401);
$file = user_file($u['code']);
$KEY = '/^(si|ss)\.(porto|star|calc)$/';

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $d = is_file($file) ? (json_decode((string)file_get_contents($file), true) ?: []) : [];
    [$fh, $db] = db_open();
    $c = $db['codes'][$u['code']] ?? [];
    $used = count(array_filter($db['sessions'], function ($s) use ($u) { return $s['code'] === $u['code']; }));
    $db['codes'][$u['code']]['seen'] = now();
    db_save($fh, $db);
    json_out(['ok' => true, 'data' => $d['data'] ?? (object)[], 'user' => [
        'name' => $c['name'] ?? '', 'code' => $u['code'], 'exp' => $c['exp'] ?? 0, 'expText' => fmt_date((int)($c['exp'] ?? 0)),
        'days' => (int)floor((($c['exp'] ?? 0) - now()) / 86400), 'devices' => $used, 'maxDevices' => $c['devices'] ?? CF_DEVICES]]);
}
if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !same_origin()) json_out(['ok' => false], 400);
$set = body()['set'] ?? null;
if (!is_array($set)) json_out(['ok' => false, 'msg' => 'format'], 422);
if (!is_dir(dirname($file))) mkdir(dirname($file), 0750, true);
$fh = fopen($file, 'c+'); flock($fh, LOCK_EX);
$d = json_decode((string)stream_get_contents($fh), true) ?: [];
$data = $d['data'] ?? [];
foreach ($set as $k => $v) {
    if (!preg_match($KEY, (string)$k)) continue;
    if ($v === null) unset($data[$k]); elseif (is_string($v)) $data[$k] = $v;
}
$out = json_encode(['data' => $data, 't' => now()], JSON_UNESCAPED_UNICODE);
if (strlen($out) > CF_USER_MAX) { flock($fh, LOCK_UN); fclose($fh); json_out(['ok' => false, 'msg' => 'Data akun melebihi batas 500 KB.'], 413); }
ftruncate($fh, 0); rewind($fh); fwrite($fh, $out); fflush($fh); flock($fh, LOCK_UN); fclose($fh);
// ringkasan untuk /daftar pengelola (jumlah posisi, tanpa isi)
$npos = 0;
foreach (['si.porto', 'ss.porto'] as $k) { $p = json_decode($data[$k] ?? '{}', true); $npos += count($p['open'] ?? []); }
[$fh, $db] = db_open();
if (isset($db['codes'][$u['code']])) { $db['codes'][$u['code']]['seen'] = now(); $db['codes'][$u['code']]['npos'] = $npos; }
db_save($fh, $db);
json_out(['ok' => true]);
