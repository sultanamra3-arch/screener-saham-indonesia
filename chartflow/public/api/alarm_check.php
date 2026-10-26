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
            if ((string)$c['tg'] === (string)CF_CHAT_ID) wa_owner("🔔 <b>Alarm harga ChartFlow</b> (" . ($m === 'id' ? 'BEI' : 'AS') . ")\n\n" . implode("\n\n", $msg));
            foreach ($fire as $a) $db['afired'][$code][] = ['t' => $a['t'], 'm' => $m, 'op' => $a['op'], 'p' => $a['p'], 'at' => $now, 'cur' => $a['cur']];
            $db['afired'][$code] = array_slice($db['afired'][$code], -20);
        } else {
            foreach ($fire as $a) { unset($a['cur']); $keep[] = $a; }   // gagal terkirim: coba lagi pada pembaruan berikutnya
            if (($r['error_code'] ?? 0) === 403) unset($db['codes'][$code]['tg']); // bot diblokir pengguna
        }
    }
    if ($keep) $db['alarms'][$code] = $keep; else unset($db['alarms'][$code]);
}
// ---- peringatan portofolio per pengguna (aturan inti yang sama dengan tab Portofolio)
$byT = []; foreach ($d['stocks'] as $o) if (isset($o['ticker'])) $byT[$o['ticker']] = $o;
$cyc = json_decode((string)@file_get_contents($base . '/cycles.json'), true) ?: [];
$broken = []; foreach ($cyc['watch']['broken'] ?? [] as $b) $broken[$b['t']] = true;
$NAMES = ['canslim' => 'CAN SLIM', 'value' => 'Value', 'growth' => 'Growth', 'quality' => 'Quality', 'dividend' => 'Dividen', 'momentum' => 'Momentum', 'swing' => 'Swing'];
$closes = function (string $t, string $since) use ($base) {
    $f = $base . '/ohlc/' . $t . '.json';
    if (!preg_match('/^[A-Z0-9.\-]{1,12}$/', $t) || !is_file($f)) return [];
    $j = json_decode((string)file_get_contents($f), true); $out = [];
    foreach ($j['b'] ?? [] as $b) if ($b[0] >= $since) $out[] = (float)$b[4];
    return $out;
};
$pkey = ($m === 'id' ? 'si' : 'ss') . '.porto';
$psent = 0;
foreach ($db['codes'] as $code => $c) {
    if (empty($c['tg']) || ($c['status'] ?? '') !== 'active' || ($c['exp'] ?? 0) < $now) continue;
    $uf = json_decode((string)@file_get_contents(user_file($code)), true) ?: [];
    $P = json_decode((string)($uf['data'][$pkey] ?? ''), true);
    $open = $P['open'] ?? [];
    $seen = $db['pnot'][$code][$m] ?? [];
    $keepSeen = []; $lines = [];
    foreach ($open as $ps) {
        $t = (string)($ps['code'] ?? ''); $o = $byT[$t] ?? null; $id = (string)($ps['id'] ?? '');
        if (!$o || empty($o['price']) || $id === '') continue;
        $p = (float)$o['price']; $buy = (float)($ps['price'] ?? 0); $meth = (string)($ps['method'] ?? 'lain');
        $st = $o['m'][$meth] ?? null;
        $stop = !empty($ps['stop']) ? (float)$ps['stop'] : null; $target = !empty($ps['target']) ? (float)$ps['target'] : null;
        $ev = [];
        $days = !empty($ps['date']) ? (int)floor(($now - strtotime($ps['date'])) / 86400) : null;
        if ($meth === 'canslim') {
            $stop = $stop ?: $buy * 0.93; $target = $target ?: $buy * 1.20;
            $cl = !empty($ps['date']) ? $closes($t, $ps['date']) : [];
            if ($cl && max(array_merge($cl, [$p])) >= $buy * 1.10 && $stop < $buy) $stop = $buy;
        } elseif ($meth === 'value') {
            $target = $target ?: $buy * 1.5;
            if ($days !== null && $days >= 730) $ev['2y'] = '⏰ sudah 2 tahun: batas waktu aturan Graham terpenuhi';
        } elseif ($meth === 'growth') {
            if (!$target && !empty($st['lv']['target'])) $target = (float)$st['lv']['target'];
        } elseif ($meth === 'quality') {
            if (!empty($st['lv']['sell']) && $p >= $st['lv']['sell']) $ev['q'] = '🔴 harga sudah sangat mahal (FCF yield < 1,5%): aturan jual Terry Smith terpenuhi';
        } elseif ($meth === 'dividend') {
            if (isset($o['payout']) && $o['payout'] > 100) $ev['pay'] = '🔴 payout di atas 100%: dividen berisiko dipotong';
        } elseif ($meth === 'momentum') {
            if (isset($o['momRank']) && $o['momRank'] < 80) $ev['mom'] = '🔴 peringkat momentum ' . round($o['momRank']) . ' (< 80): aturan jual Momentum terpenuhi';
        } elseif ($meth === 'swing') {
            $cl = $closes($t, '0000'); $a5 = array_slice($cl, -5);
            if (count($a5) === 5 && $p > array_sum($a5) / 5) $ev['s5'] = '🔴 harga sudah di atas rata-rata 5 hari: aturan jual Connors terpenuhi';
        }
        if ($st && ($st['s'] ?? '') === 'sell') $ev['sell'] = '🔴 tanda jual metode ' . ($NAMES[$meth] ?? $meth) . (!empty($st['rs']) ? ': ' . $st['rs'] : '');
        if ($stop && $p <= $stop) $ev['stop'] = '🛑 harga menyentuh batas rugi ' . money_fmt($stop, $m) . ' (aturan stop)';
        if ($target && $p >= $target) $ev['tgt'] = '🎯 target ' . money_fmt($target, $m) . ' tercapai (aturan target' . ($meth === 'canslim' ? " O'Neil" : '') . ')';
        if (isset($broken[$t])) $ev['brk:' . $day] = '⚠️ harga ditutup di bawah lantai harga (support) hari ini';
        $keys = array_keys($ev);
        $keepSeen[$id] = array_values(array_filter($keys, function ($k) { return strpos($k, 'brk:') !== 0; }));
        $new = array_diff($keys, $seen[$id] ?? []);
        if (!$new) continue;
        $pl = $buy > 0 ? ($p / $buy - 1) * 100 : 0;
        $lines[] = '<b>' . h($t) . '</b> ' . money_fmt($p, $m) . ' (' . ($pl >= 0 ? '+' : '') . number_format($pl, 1, ',', '.') . '% dari harga beli)' . "\n" . implode("\n", array_map(function ($k) use ($ev) { return h($ev[$k]); }, $new));
    }
    if ($lines) {
        $r = tg('sendMessage', ['chat_id' => $c['tg'], 'parse_mode' => 'HTML', 'disable_web_page_preview' => true,
            'text' => "💼 <b>Portofolio ChartFlow</b> (" . ($m === 'id' ? 'BEI' : 'AS') . ")\n\n" . implode("\n\n", $lines) . "\n\n<i>Informasi otomatis dari aturan metode yang Anda pilih, bukan ajakan membeli atau menjual. Keputusan sepenuhnya di tangan Anda. Peringatan yang sama tidak dikirim ulang.</i>"]);
        if (empty($r['ok'])) continue;   // gagal: coba lagi pada pembaruan berikutnya
        $psent++;
        if ((string)$c['tg'] === (string)CF_CHAT_ID) wa_owner("💼 <b>Portofolio ChartFlow</b> (" . ($m === 'id' ? 'BEI' : 'AS') . ")\n\n" . implode("\n\n", $lines));
    }
    $db['pnot'][$code][$m] = $keepSeen;
}
db_save($fh, $db);
json_out(['ok' => true, 'm' => $m, 'date' => $day, 'hits' => $hits, 'sent' => $sent, 'porto' => $psent]);
