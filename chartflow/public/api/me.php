<?php
require __DIR__ . '/lib.php';
$u = session_user();
json_out($u ? ['ok' => true, 'name' => $u['name'], 'exp' => fmt_date($u['exp'])] : ['ok' => false]);
