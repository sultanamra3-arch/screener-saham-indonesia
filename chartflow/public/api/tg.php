<?php
// Webhook Telegram: tombol Setujui/Tolak dan perintah pengelola. Hanya chat pengelola yang dilayani.
require __DIR__ . '/lib.php';
if (!hash_equals(CF_HOOK_SECRET, $_SERVER['HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN'] ?? '')) { http_response_code(403); exit; }
$u = json_decode((string)file_get_contents('php://input'), true) ?: [];
const SITE = 'https://chartflow.my.id';

function wa_link(string $contact, string $text): ?string {
    $d = preg_replace('/\D/', '', $contact);
    if (strlen($d) < 9) return null;
    if (strpos($d, '0') === 0) $d = '62' . substr($d, 1);
    return 'https://wa.me/' . $d . '?text=' . rawurlencode($text);
}
function share_text(string $code, int $exp): string {
    return "Halo! Ini kode akses ChartFlow Anda: $code\nBerlaku sampai " . fmt_date($exp) . ", untuk maksimal " . CF_DEVICES . " perangkat.\nMasuk di " . SITE . " lalu tekan \"Masuk\".";
}
function reply(string $t, array $extra = []): void { tg('sendMessage', ['chat_id' => CF_CHAT_ID, 'text' => $t, 'parse_mode' => 'HTML', 'disable_web_page_preview' => true] + $extra); }

// ---- tombol
if (isset($u['callback_query'])) {
    $q = $u['callback_query'];
    if ((string)($q['message']['chat']['id'] ?? '') !== (string)CF_CHAT_ID) exit;
    $p = explode(':', (string)($q['data'] ?? ''));
    [$fh, $db] = db_open();
    $r = $db['reqs'][$p[1] ?? ''] ?? null;
    if (!$r || $r['status'] !== 'pending') { db_close($fh); tg('answerCallbackQuery', ['callback_query_id' => $q['id'], 'text' => 'Sudah diproses.']); exit; }
    $orig = $q['message']['text'] ?? '';
    if ($p[0] === 'ok') {
        $days = max(1, min(3650, (int)($p[2] ?? CF_DAYS)));
        do { $code = new_code(); } while (isset($db['codes'][$code]));
        $exp = now() + $days * 86400;
        $db['codes'][$code] = ['name' => $r['name'], 'contact' => $r['contact'], 'status' => 'active', 'created' => now(), 'exp' => $exp, 'devices' => CF_DEVICES];
        $db['reqs'][$p[1]]['status'] = 'ok'; $db['reqs'][$p[1]]['code'] = $code;
        db_save($fh, $db);
        tg('editMessageText', ['chat_id' => CF_CHAT_ID, 'message_id' => $q['message']['message_id'], 'text' => $orig . "\n\n✅ Disetujui $days hari", 'parse_mode' => 'HTML']);
        $share = share_text($code, $exp);
        $wa = wa_link($r['contact'], $share);
        reply("🔑 Kode untuk <b>" . h($r['name']) . "</b>:\n<code>$code</code>\nBerlaku sampai " . fmt_date($exp) . ".\n\nTeruskan pesan di bawah ke " . h($r['contact']) . ":\n\n<code>" . h($share) . "</code>",
            $wa ? ['reply_markup' => ['inline_keyboard' => [[['text' => '📲 Kirim lewat WhatsApp', 'url' => $wa]]]]] : []);
    } else {
        $db['reqs'][$p[1]]['status'] = 'no';
        db_save($fh, $db);
        tg('editMessageText', ['chat_id' => CF_CHAT_ID, 'message_id' => $q['message']['message_id'], 'text' => $orig . "\n\n❌ Ditolak", 'parse_mode' => 'HTML']);
    }
    tg('answerCallbackQuery', ['callback_query_id' => $q['id']]);
    exit;
}

// ---- perintah teks
$m = $u['message'] ?? null;
if (!$m || (string)($m['chat']['id'] ?? '') !== (string)CF_CHAT_ID) exit;
$t = trim((string)($m['text'] ?? ''));
if ($t === '' || $t[0] !== '/') exit;
$a = preg_split('/\s+/', $t); $cmd = strtolower(explode('@', $a[0])[0]);

if ($cmd === '/daftar') {
    [$fh, $db] = db_open(); prune($db); $codes = $db['codes']; $sess = $db['sessions']; db_save($fh, $db);
    $now = now(); $lines = [];
    uasort($codes, function ($x, $y) { return $y['exp'] <=> $x['exp']; });
    foreach ($codes as $c => $v) {
        if ($v['status'] !== 'active') continue;
        $dev = count(array_filter($sess, function ($s) use ($c) { return $s['code'] === $c; }));
        $lines[] = ($v['exp'] < $now ? '⌛ ' : '🟢 ') . "<code>$c</code> " . h($v['name'] ?? '') . " · s.d. " . fmt_date($v['exp']) . " · $dev/" . ($v['devices'] ?? CF_DEVICES) . " perangkat";
    }
    reply($lines ? "<b>Kode aktif</b>\n" . implode("\n", array_slice($lines, 0, 60)) : 'Belum ada kode aktif.');
} elseif (in_array($cmd, ['/cabut', '/perpanjang', '/reset'], true)) {
    $code = norm_code($a[1] ?? '');
    [$fh, $db] = db_open();
    if (!$code || !isset($db['codes'][$code])) { db_close($fh); reply('Kode tidak ditemukan. Contoh: <code>' . $cmd . ' CF-ABCD-2345</code>'); exit; }
    if ($cmd === '/cabut') {
        $db['codes'][$code]['status'] = 'revoked';
        foreach ($db['sessions'] as $k => $s) if ($s['code'] === $code) unset($db['sessions'][$k]);
        $msg = "🚫 <code>$code</code> dicabut. Semua perangkatnya keluar.";
    } elseif ($cmd === '/reset') {
        foreach ($db['sessions'] as $k => $s) if ($s['code'] === $code) unset($db['sessions'][$k]);
        $msg = "♻️ Perangkat untuk <code>$code</code> direset. Pemilik bisa masuk lagi di perangkat baru.";
    } else {
        $days = max(1, min(3650, (int)($a[2] ?? CF_DAYS)));
        $db['codes'][$code]['exp'] = max(now(), $db['codes'][$code]['exp']) + $days * 86400;
        $db['codes'][$code]['status'] = 'active';
        $msg = "⏳ <code>$code</code> diperpanjang $days hari, sampai " . fmt_date($db['codes'][$code]['exp']) . '.';
    }
    db_save($fh, $db); reply($msg);
} elseif ($cmd === '/kode') {
    $days = max(1, min(3650, (int)($a[1] ?? CF_DAYS)));
    $name = trim(implode(' ', array_slice($a, 2))) ?: 'Manual';
    [$fh, $db] = db_open();
    do { $code = new_code(); } while (isset($db['codes'][$code]));
    $exp = now() + $days * 86400;
    $db['codes'][$code] = ['name' => $name, 'contact' => '', 'status' => 'active', 'created' => now(), 'exp' => $exp, 'devices' => CF_DEVICES];
    db_save($fh, $db);
    reply("🔑 Kode baru untuk " . h($name) . ":\n<code>$code</code>\nBerlaku sampai " . fmt_date($exp) . ".\n\n<code>" . h(share_text($code, $exp)) . "</code>");
} else {
    reply("<b>Perintah ChartFlow</b>\n/daftar: kode aktif dan jumlah perangkat\n/kode 30 Nama: buat kode baru (hari, nama)\n/perpanjang KODE 30: tambah masa berlaku\n/reset KODE: keluarkan semua perangkat kode itu\n/cabut KODE: matikan kode\n\nPermintaan dari website datang otomatis dengan tombol Setujui/Tolak.");
}
