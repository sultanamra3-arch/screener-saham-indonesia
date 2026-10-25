<?php
// Pengunjung meminta kode akses -> pesan ke Telegram pengelola dengan tombol Setujui/Tolak.
require __DIR__ . '/lib.php';
if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !same_origin()) json_out(['ok' => false, 'msg' => 'Permintaan tidak sah.'], 400);
$b = body();
$name = trim(mb_substr((string)($b['name'] ?? ''), 0, 60));
$contact = trim(mb_substr((string)($b['contact'] ?? ''), 0, 60));
$why = trim(mb_substr((string)($b['why'] ?? ''), 0, 200));
if (!empty($b['website'])) json_out(['ok' => true]); // jebakan bot spam
if (mb_strlen($name) < 2 || mb_strlen($contact) < 4) json_out(['ok' => false, 'msg' => 'Isi nama dan kontak dengan benar.'], 422);

[$fh, $db] = db_open();
if (!rate_ok($db, 'req', 3, 3600)) { db_save($fh, $db); json_out(['ok' => false, 'msg' => 'Terlalu banyak permintaan. Coba lagi dalam 1 jam.'], 429); }
$id = rnd(6);
$db['reqs'][$id] = ['t' => now(), 'name' => $name, 'contact' => $contact, 'why' => $why, 'status' => 'pending'];
prune($db);
db_save($fh, $db);

$txt = "📩 <b>Permintaan akses ChartFlow</b>\n👤 " . h($name) . "\n📞 " . h($contact) . ($why ? "\n💬 " . h($why) : '') . "\n🕒 " . fmt_date(now());
tg('sendMessage', ['chat_id' => CF_CHAT_ID, 'text' => $txt, 'parse_mode' => 'HTML',
    'reply_markup' => ['inline_keyboard' => [[
        ['text' => '✅ Setujui 30 hari', 'callback_data' => "ok:$id:30"],
        ['text' => '✅ 90 hari', 'callback_data' => "ok:$id:90"],
        ['text' => '❌ Tolak', 'callback_data' => "no:$id"]]]]]);
json_out(['ok' => true, 'msg' => 'Permintaan terkirim. Kode akan dikirim ke kontak Anda setelah disetujui.']);
