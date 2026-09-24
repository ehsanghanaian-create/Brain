<?php
header('Content-Type: application/json');header('Cache-Control: private, no-store');
try {
    $private=dirname(__DIR__).'/ead-access';
    require $private.'/core.php';require $private.'/entry_core.php';
    $result=EADEntry::record($private,$_SERVER,file_get_contents('php://input',false,null,0,1025));
    http_response_code(202);echo json_encode($result);
} catch(Throwable $e) {
    http_response_code(in_array($e->getMessage(),array('rate','capacity'),true)?429:400);
    echo '{"accepted":false}';
}
