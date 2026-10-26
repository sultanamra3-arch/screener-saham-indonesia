<?php
// Dipanggil GitHub Actions setelah data pasar dikirim: periksa alarm harga semua akun, kirim Telegram, matikan alarm yang berbunyi.
require __DIR__ . '/lib.php';
if (!hash_equals(CF_HOOK_SECRET, (string)($_POST['k'] ?? ''))) { http_response_code(403); exit; }
$m = ($_POST['m'] ?? '') === 'us' ? 'us' : 'id';
$base = realpath(__DIR__ . '/../_appfiles/' . $m . '/data');
$d = $base ? json_decode((string)@file_get_contents($base . '/stocks.json'), true) : null;
if (!$d || empty($d['stocks'])) json_out(['ok' => false, 'msg' => 'data belum ada'], 500);
$day = (string)($d['priceDate'] ?? '');
$px = [];
foreach ($d['stocks'] as $o) if (isset($o['ticker'], $o['price'])) $px[$o['ticker']] = (float)$o['price'];
$hl = function (string $t) use ($base, $day, &$px) {   // harga tertinggi/terendah hari ini dari data candlestick
    $f = $base . '/ohlc/' . $t . '.json';
    if (preg_match('/^[A-Z0-9.\-]{1,12}$/', $t) && is_file($f)) {
        $j = json_decode((string)file_get_contents($f), true); $b = $j['b'] ?? [];
        $last = end($b);
        if ($last && $last[0] === $day) return [(float)$last[2], (float)$last[3]];
    }
    return isset($px[$t]) ? [$px[$t], $px[$t]] : null;
};
[$fh, $db] = db_open();
$sent = 0; $hits = 0; $now = now();
foreach ($db['alarms'] ?? [] as $code => $list) {
    $c = $db['codes'][$code] ?? null;
    if (!$c || ($c['status'] ?? '') !== 'active' || ($c['exp'] ?? 0) < $now) continue;
    $keep = []; $msg = []; $fire = [];
    foreach ($list as $a) {
        if ($a['m'] !== $m) { $keep[] = $a; continue; }
        $r = $hl($a['t']);
        $hit = $r && ($a['op'] === 'le' ? $r[1] <= $a['p'] : $r[0] >= $a['p']);
        if (!$hit || empty($c['tg'])) { $keep[] = $a; continue; }
        $hits++;
        $cur = $px[$a['t']] ?? null;
        $msg[] = '<b>' . h($a['t']) . '</b> ' . ($a['op'] === 'le' ? 'turun ke ≤ ' : 'naik ke ≥ ') . money_fmt($a['p'], $m)
            . ' (' . ($a['op'] === 'le' ? 'terendah ' . money_fmt($r[1], $m) : 'tertinggi ' . money_fmt($r[0], $m)) . ($cur ? ', sekarang ' . money_fmt($cur, $m) : '') . ')'
            . ($a['note'] ? "\n<i>" . h($a['note']) . '</i>' : '');
        $fire[] = $a + ['cur' => $cur];
    }
    if ($msg) {
        $r = tg('sendMessage', ['chat_id' => $c['tg'], 'parse_mode' => 'HTML', 'disable_web_page_preview' => true,
            'text' => "🔔 <b>Alarm harga ChartFlow</b> (" . ($m === 'id' ? 'BEI' : 'AS') . ")\n\n" . implode("\n\n", $msg) . "\n\nAlarm ini sudah dimatikan. Pasang lagi di https://chartflow.my.id bila perlu.\n<i>Harga dari pembaruan data terakhir, bukan real-time.</i>"]);
        if (!empty($r['ok'])) {
            $sent++;
            foreach ($fire as $a) $db['afired'][$code][] = ['t' => $a['t'], 'm' => $m, 'op' => $a['op'], 'p' => $a['p'], 'at' => $now, 'cur' => $a['cur']];
            $db['afired'][$code] = array_slice($db['afired'][$code], -20);
        } else {
            foreach ($fire as $a) { unset($a['cur']); $keep[] = $a; }   // gagal terkirim: coba lagi pada pembaruan berikutnya
            if (($r['error_code'] ?? 0) === 403) unset($db['codes'][$code]['tg']); // bot diblokir pengguna
        }
    }
    if ($keep) $db['alarms'][$code] = $keep; else unset($db['alarms'][$code]);
}
db_save($fh, $db);
json_out(['ok' => true, 'm' => $m, 'date' => $day, 'hits' => $hits, 'sent' => $sent]);
