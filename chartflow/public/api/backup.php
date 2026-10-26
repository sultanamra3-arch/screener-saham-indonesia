<?php
// Cadangan mingguan data akun -> dikirim ke Telegram pengelola. Dipanggil terjadwal dari GitHub Actions.
require __DIR__ . '/lib.php';
if (!hash_equals(CF_HOOK_SECRET, (string)($_POST['k'] ?? ''))) { http_response_code(403); exit; }
$dir = __DIR__ . '/../_data';
$users = [];
foreach (glob($dir . '/users/*.json') ?: [] as $f) $users[basename($f)] = json_decode((string)file_get_contents($f), true);
$db = json_decode((string)@file_get_contents($dir . '/db.json'), true) ?: [];
$pack = json_encode(['t' => date('c'), 'db' => $db, 'users' => $users], JSON_UNESCAPED_UNICODE);
$tmp = tempnam(sys_get_temp_dir(), 'cfb');
file_put_contents($tmp, gzencode($pack, 9));
$active = count(array_filter($db['codes'] ?? [], function ($c) { return ($c['status'] ?? '') === 'active' && ($c['exp'] ?? 0) > time(); }));
$name = 'chartflow-cadangan-' . date('Y-m-d') . '.json.gz';
$quiet = (new DateTime('now', new DateTimeZone('Asia/Jakarta')))->format('w') !== '0'; // Minggu berbunyi, hari lain senyap
$ch = curl_init('https://api.telegram.org/bot' . CF_BOT_TOKEN . '/sendDocument');
curl_setopt_array($ch, [CURLOPT_POST => true, CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 60, CURLOPT_POSTFIELDS => [
    'chat_id' => CF_CHAT_ID, 'parse_mode' => 'HTML', 'disable_notification' => $quiet ? 'true' : 'false',
    'caption' => "🗄️ <b>Cadangan " . ($quiet ? 'harian' : 'mingguan') . " ChartFlow</b>\n$active kode aktif · " . count($users) . " akun dengan data.\nSimpan file ini; berisi data pribadi pengguna, jangan dibagikan.",
    'document' => new CURLFile($tmp, 'application/gzip', $name)]]);
$r = curl_exec($ch); curl_close($ch); @unlink($tmp);
header('Content-Type: application/json');
echo json_encode(['ok' => (bool)$r && strpos((string)$r, '"ok":true') !== false]);
