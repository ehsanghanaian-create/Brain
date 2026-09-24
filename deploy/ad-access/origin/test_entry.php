<?php
require __DIR__.'/core.php';require __DIR__.'/entry_core.php';
$dir=sys_get_temp_dir().'/ead-entry-'.bin2hex(random_bytes(5));mkdir($dir);
$server=array('HTTPS'=>'on','REQUEST_METHOD'=>'POST','HTTP_ORIGIN'=>'https://modirankhodro-emdad.com','REMOTE_ADDR'=>'8.8.4.4','HTTP_X_FORWARDED_FOR'=>'1.1.1.1');
$p=array('gclid'=>str_repeat('C',30),'navigation_type'=>'navigate','utm_campaign'=>'qa-origin');$n=0;
function good($x){global $n;if(!$x)throw new Exception('assertion');$n++;}
function bad($s,$p){global $dir;try{EADEntry::record($dir,$s,json_encode($p),1000);}catch(RuntimeException $e){good(true);return;}throw new Exception('expected refusal');}
try {
 $x=$server;$x['REQUEST_METHOD']='GET';bad($x,$p);
 $x=$server;$x['HTTP_ORIGIN']='https://evil.invalid';bad($x,$p);
 $x=$p;$x['ip']='1.1.1.1';bad($server,$x);
 $x=$p;$x['gclid']=str_repeat('A',257);bad($server,$x);
 $x=$p;$x['navigation_type']='reload';bad($server,$x);
 good(EADEntry::record($dir,$server,json_encode($p),1000)===array('accepted'=>true));
 good(EADEntry::read($dir)['entries']===array());
 $r=EADEntry::read($dir,0);good($r['entries'][0]['ip_address']==='8.8.4.4');good($r['entries'][0]['utm_campaign']==='qa-origin');
 good(EADEntry::read($dir,1)['entries']===array());
 for($i=0;$i<9;$i++)EADEntry::record($dir,$server,json_encode($p),1000);
 bad($server,$p);EADEntry::record($dir,$server,json_encode($p),1060);good(EADEntry::read($dir)['last_id']===11);
 echo $n." entry checks passed\n";
}finally{foreach(glob($dir.'/*')as$f)unlink($f);rmdir($dir);}
