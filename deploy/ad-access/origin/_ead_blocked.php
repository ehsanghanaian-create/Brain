<?php
declare(strict_types=1);

http_response_code(403);
header('Content-Type: text/html; charset=UTF-8');
header('Cache-Control: no-store, private');
header('X-Robots-Tag: noindex, nofollow, noarchive');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');
header("Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'");

// REMOTE_ADDR is supplied by the web server. Never trust a visitor-supplied forwarding header here.
$remoteAddress = (string) ($_SERVER['REMOTE_ADDR'] ?? '');
$displayAddress = filter_var($remoteAddress, FILTER_VALIDATE_IP) ? $remoteAddress : 'نامشخص';
$escapedAddress = htmlspecialchars($displayAddress, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
?>
<!doctype html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="noindex,nofollow,noarchive">
    <title>دسترسی محدود شده است</title>
    <style>
        * { box-sizing: border-box; }
        body { min-height: 100vh; display: grid; place-items: center; margin: 0; padding: 20px; background: #f3f7f4; color: #18392d; font-family: Tahoma, Arial, sans-serif; }
        main { width: min(100%, 610px); padding: clamp(24px, 6vw, 46px); border: 1px solid #dce9df; border-radius: 24px; background: #fff; box-shadow: 0 20px 55px #183c2514; }
        .brand { font-size: 14px; font-weight: 700; color: #147d59; }
        .line { width: 48px; height: 4px; margin: 25px 0 22px; border-radius: 8px; background: #d48232; }
        h1 { margin: 0 0 14px; font-size: clamp(23px, 5vw, 31px); line-height: 1.6; }
        p { margin: 0 0 16px; color: #465d50; font-size: 15px; line-height: 2; }
        .ip { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; margin: 22px 0; padding: 15px 18px; border: 1px solid #e4ece6; border-radius: 14px; background: #f8faf8; font-size: 14px; }
        .ip strong { color: #18392d; direction: ltr; unicode-bidi: isolate; font-family: Consolas, monospace; font-size: 16px; }
        .notice { padding-right: 16px; border-right: 3px solid #d48232; }
        .foot { margin-top: 26px; padding-top: 18px; border-top: 1px solid #e7eee9; color: #718077; font-size: 13px; line-height: 1.9; }
        @media (max-width: 600px) { main { border-radius: 18px; } .ip { display: block; } .ip strong { display: block; margin-top: 8px; overflow-wrap: anywhere; } }
    </style>
</head>
<body>
<main>
    <div class="brand">مدیران خودرو امداد</div>
    <div class="line"></div>
    <h1>دسترسی از این نشانی محدود شده است</h1>
    <p>الگوی مراجعه از این نشانی برای بررسی سوءاستفاده احتمالی از تبلیغات و حفاظت از خدمات سایت ثبت شده است.</p>
    <div class="ip"><span>نشانی IP این درخواست:</span> <strong lang="en"><?= $escapedAddress ?></strong></div>
    <p class="notice">اگر بررسی فنی نشان دهد ورودهای عمدی از مسیر تبلیغات با هدف تحمیل هزینه یا ورود خسارت انجام شده، حق پیگیری موضوع از مراجع قانونی و مطالبه خسارت برای این کسب‌وکار محفوظ است.</p>
    <div class="foot">نشانی IP به‌تنهایی هویت شخص را مشخص نمی‌کند. اگر این محدودیت را اشتباه می‌دانید، درخواست بررسی را از راه ارتباطی کسب‌وکار ثبت کنید.</div>
</main>
</body>
</html>
