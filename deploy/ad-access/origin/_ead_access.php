<?php
/* Install only this entry point in public_html. */
header('Content-Type: application/json');header('Cache-Control: private, no-store');
try {
    if(($_SERVER['REQUEST_METHOD']??'')!=='POST') {http_response_code(405);echo '{"error":"method"}';exit;}
    if(empty($_SERVER['HTTPS']) || $_SERVER['HTTPS']==='off') {http_response_code(403);echo '{"error":"tls_required"}';exit;}
    $private=dirname(__DIR__).'/ead-access';
    $cfg=require $private.'/config.php';
    $cfg['private_dir']=$private;$cfg['root']=__DIR__;
    require $private.'/core.php';
    $raw=file_get_contents('php://input',false,null,0,4097);
    $result=(new EADAccess($cfg))->handle($raw,$_SERVER['HTTP_X_EAD_SIGNATURE']??'',$_SERVER);
    echo json_encode($result);
} catch(Throwable $e) {
    http_response_code($e->getMessage()==='unauthorized'?401:409);
    $known=array('unauthorized','invalid_request','invalid_payload','invalid_action','enforcement_disabled','protected_ip','nonce_conflict','decision_owner_conflict','invalid_decision_id','invalid_ip','htaccess_changed_retry');
    echo json_encode(array('error'=>in_array($e->getMessage(),$known,true)?$e->getMessage():'operation_failed'));
}
