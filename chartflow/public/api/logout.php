<?php
require __DIR__ . '/lib.php';
$tok = $_COOKIE[CF_COOKIE] ?? '';
if (preg_match('/^[a-f0-9]{64}$/', $tok)) { [$fh, $db] = db_open(); unset($db['sessions'][hash('sha256', $tok)]); db_save($fh, $db); }
setcookie(CF_COOKIE, '', ['expires' => 1, 'path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Lax']);
header('Location: /'); exit;
