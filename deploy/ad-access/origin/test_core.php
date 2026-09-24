<?php
require __DIR__.'/core.php';
$temp=sys_get_temp_dir().'/ead-test-'.bin2hex(random_bytes(6));mkdir($temp);mkdir($temp.'/public_html');mkdir($temp.'/ead-access');
$cfg=array('site'=>'modirankhodro-emdad.com','secret'=>str_repeat('x',40),'enforcement_enabled'=>true,
 'root'=>$temp.'/public_html','private_dir'=>$temp.'/ead-access','protected_ips'=>array('8.8.8.8'),'protected_ranges'=>array('9.9.9.0/24'));
$old="# existing manual rules\r\nDeny from 1.2.3.4\r\n# WordPress\nRewriteRule . /index.php [L]\n";
file_put_contents($cfg['root'].'/.htaccess',$old);$core=new EADAccess($cfg);$checks=0;$counter=0;
function ok($v,$msg) {global $checks;if(!$v) throw new Exception($msg);$checks++;}
function request($action,$ip='8.8.4.4',$id='decision_000000001',$extra=array()) {global $counter;return array_merge(array('site'=>'modirankhodro-emdad.com','action'=>$action,'ip'=>$ip,'decision_id'=>$id,'ts'=>1000,'nonce'=>'nonce_'.str_pad(++$counter,20,'0',STR_PAD_LEFT)),$extra);}
function callit($p,$hook=null) {global $core,$cfg;$raw=json_encode($p);return $core->handle($raw,hash_hmac('sha256',$raw,$cfg['secret']),array('REMOTE_ADDR'=>'8.8.8.8'),1000,$hook);}
function refused($fn,$reason) {try{$fn();}catch(RuntimeException $e){ok($e->getMessage()===$reason,'wrong refusal '.$e->getMessage());return;}throw new Exception('not refused '.$reason);}
try {
 callit(request('status'));ok(!file_exists($cfg['private_dir'].'/state.json'),'status mutated state');
 refused(function()use($core){$core->handle('{}','bad',array(),1000);},'unauthorized');
 refused(function(){callit(request('status','8.8.4.4','decision_000000001',array('ts'=>939)));},'invalid_request');
 foreach(array('8.8.8.8','9.9.9.9','127.0.0.1') as $ip) refused(function()use($ip){callit(request('block',$ip));},'protected_ip');
 $p=request('block');$r=callit($p);ok($r['active'],'block failed');$render=file_get_contents($cfg['root'].'/.htaccess');
 ok(substr($render,-strlen($old))===$old,'nonowned bytes changed');ok(strpos($render,'RewriteCond %{REMOTE_ADDR} ^8\\.8\\.4\\.4$')!==false,'IP regex');
 callit($p);ok(file_get_contents($cfg['root'].'/.htaccess')===$render,'retry changed render');
 $bad=$p;$bad['ip']='1.1.1.1';refused(function()use($bad){callit($bad);},'nonce_conflict');
 callit(request('unblock'));ok(!callit(request('block'))['active'],'cancelled id resurrected');
 callit(request('block','8.8.4.4','decision_000000002'));callit(request('unblock'));
 ok(strpos(file_get_contents($cfg['root'].'/.htaccess'),'8\\.8\\.4\\.4')!==false,'old unblock removed new owner');
 $p=request('block','1.1.1.1','decision_000000003');
 refused(function()use($p,$cfg){callit($p,function()use($cfg){file_put_contents($cfg['root'].'/.htaccess',"# external edit\n",FILE_APPEND);});},'htaccess_changed_retry');
 callit($p);$result=file_get_contents($cfg['root'].'/.htaccess');ok(strpos($result,'# external edit')!==false,'CAS retry lost edit');ok(strpos($result,'1\\.1\\.1\\.1')!==false,'retry did not reconcile');
 $disabled=$cfg;$disabled['enforcement_enabled']=false;$dc=new EADAccess($disabled);$p=request('block');$raw=json_encode($p);
 refused(function()use($dc,$raw,$cfg){$dc->handle($raw,hash_hmac('sha256',$raw,$cfg['secret']),array(),1000);},'enforcement_disabled');
 echo $checks." origin checks passed\n";
} finally {
 foreach(glob($temp.'/public_html/*') as $f) unlink($f);
 foreach(glob($temp.'/public_html/.*') as $f) if(is_file($f)) unlink($f);
 foreach(glob($temp.'/ead-access/*') as $f) unlink($f);
 rmdir($temp.'/public_html');rmdir($temp.'/ead-access');rmdir($temp);
}
