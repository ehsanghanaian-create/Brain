<?php
/* PHP 7.4; no WordPress dependency. Fixed-path, signed origin controller. */
class EADAccess {
    const BEGIN = '# BEGIN EAD PERMANENT ACCESS';
    const END = '# END EAD PERMANENT ACCESS';
    private $cfg;
    public function __construct($cfg) {
        $this->cfg=$cfg;
        if (($cfg['site']??'')!=='modirankhodro-emdad.com' || strlen($cfg['secret']??'')<32) throw new RuntimeException('invalid_config');
    }
    public static function ip($s) {
        if (!is_string($s) || !filter_var($s,FILTER_VALIDATE_IP)) throw new RuntimeException('invalid_ip');
        return inet_ntop(inet_pton($s));
    }
    private function protectedIP($ip) {
        if (!filter_var($ip,FILTER_VALIDATE_IP,FILTER_FLAG_NO_PRIV_RANGE|FILTER_FLAG_NO_RES_RANGE)) return true;
        foreach (($this->cfg['protected_ips']??array()) as $p) if (self::ip($p)===$ip) return true;
        foreach (($this->cfg['protected_ranges']??array()) as $cidr) {
            $parts=explode('/',$cidr); $net=inet_pton($parts[0]); $addr=inet_pton($ip);
            if ($net===false || count($parts)!==2) throw new RuntimeException('invalid_protected_range');
            $bits=(int)$parts[1]; if($bits<0 || $bits>strlen($net)*8) throw new RuntimeException('invalid_protected_range');
            if(strlen($addr)!==strlen($net)) continue;
            $bytes=intdiv($bits,8);$rest=$bits%8;
            if(substr($addr,0,$bytes)===substr($net,0,$bytes) && (!$rest || ((ord($addr[$bytes]) ^ ord($net[$bytes])) & (255 << (8-$rest)))===0)) return true;
        }
        return false;
    }
    public static function render($original,$ips) {
        $begin=strpos($original,self::BEGIN);$end=strpos($original,self::END);
        if(($begin===false)!==($end===false)) throw new RuntimeException('invalid_owned_markers');
        if($begin!==false) {
            if($begin!==0 || substr_count($original,self::BEGIN)!==1 || substr_count($original,self::END)!==1) throw new RuntimeException('invalid_owned_markers');
            $after=$end+strlen(self::END);
            if(substr($original,$after,2)==="\r\n") $after+=2;
            elseif(substr($original,$after,1)==="\n") $after++;
            $original=substr($original,$after);
        }
        $ips=array_values(array_unique($ips));sort($ips,SORT_STRING);
        $block=self::BEGIN."\nRewriteEngine On\n";
        foreach($ips as $i=>$ip) $block.='RewriteCond %{REMOTE_ADDR} ^'.preg_quote(self::ip($ip),'~').'$'.($i<count($ips)-1?' [OR]':'')."\n";
        if($ips) $block.="RewriteRule ^ - [F,L]\n";
        return $block.self::END."\n".$original;
    }
    public static function atomic($path,$bytes) {
        $tmp=tempnam(dirname($path),'.ead-');if($tmp===false) throw new RuntimeException('temp_failed');
        try {
            if(file_put_contents($tmp,$bytes)!==strlen($bytes)) throw new RuntimeException('write_failed');
            chmod($tmp,0600);
            if(!rename($tmp,$path)) throw new RuntimeException('rename_failed');
        } finally {if(is_file($tmp)) unlink($tmp);}
    }
    private function audit($entry) {
        $entry['at']=time();$line=json_encode($entry,JSON_UNESCAPED_SLASHES)."\n";
        if(file_put_contents($this->cfg['private_dir'].'/audit.jsonl',$line,FILE_APPEND)!==strlen($line)) throw new RuntimeException('audit_failed');
    }
    private function reconcile($state,$beforeRename=null) {
        $path=$this->cfg['root'].'/.htaccess';
        if(is_link($path)) throw new RuntimeException('symlink_refused');
        $old=is_file($path)?file_get_contents($path):'';if($old===false) throw new RuntimeException('read_failed');
        $ips=array();foreach($state['decisions'] as $d) if($d['active']) $ips[]=$d['ip'];
        $new=self::render($old,$ips);if($new===$old) return hash('sha256',$new);
        $backup=$this->cfg['private_dir'].'/before-'.hash('sha256',$old).'.htaccess';
        if(!file_exists($backup)) self::atomic($backup,$old);
        $tmp=tempnam(dirname($path),'.ead-');if($tmp===false) throw new RuntimeException('temp_failed');
        try {
            if(file_put_contents($tmp,$new)!==strlen($new)) throw new RuntimeException('write_failed');
            chmod($tmp,is_file($path)?(fileperms($path)&0777):0644);
            if($beforeRename) $beforeRename(); // test-only dependency injection; never supplied by receiver.
            $current=is_file($path)?file_get_contents($path):'';
            if($current!==$old) throw new RuntimeException('htaccess_changed_retry');
            if(!rename($tmp,$path)) throw new RuntimeException('rename_failed');
            if(file_get_contents($path)!==$new) throw new RuntimeException('readback_failed');
        } finally {if(is_file($tmp)) unlink($tmp);}
        return hash('sha256',$new);
    }
    public function handle($raw,$signature,$server=array(),$now=null,$beforeRename=null) {
        $now=$now??time();if(strlen($raw)>4096 || !is_string($signature) || !hash_equals(hash_hmac('sha256',$raw,$this->cfg['secret']),$signature)) throw new RuntimeException('unauthorized');
        $p=json_decode($raw,true);
        if(!is_array($p) || array_diff(array_keys($p),array('site','action','ip','decision_id','ts','nonce','since'))) throw new RuntimeException('invalid_payload');
        if(($p['site']??'')!==$this->cfg['site'] || !is_int($p['ts']??null) || abs($now-$p['ts'])>60 || !preg_match('/^[A-Za-z0-9_-]{16,96}$/D',$p['nonce']??'')) throw new RuntimeException('invalid_request');
        $action=$p['action']??'';if(!in_array($action,array('status','entries','block','unblock'),true)) throw new RuntimeException('invalid_action');
        if($action==='entries') {
            require_once __DIR__.'/entry_core.php';
            if(isset($p['since']) && (!is_int($p['since']) || $p['since']<0)) throw new RuntimeException('invalid_since');
            return EADEntry::read($this->cfg['private_dir'],$p['since']??null);
        }
        $private=$this->cfg['private_dir'];$lock=fopen($private.'/lock','c');if(!$lock || !flock($lock,LOCK_EX)) throw new RuntimeException('lock_failed');
        try {
            $path=$private.'/state.json';$state=is_file($path)?json_decode(file_get_contents($path),true):array('decisions'=>array(),'nonces'=>array());
            if(!is_array($state) || !isset($state['decisions'],$state['nonces'])) throw new RuntimeException('state_invalid');
            $digest=hash('sha256',$raw);$nonce=$p['nonce'];
            if(isset($state['nonces'][$nonce]) && $state['nonces'][$nonce]['digest']!==$digest) throw new RuntimeException('nonce_conflict');
            foreach($state['nonces'] as $k=>$v) if($v['ts']<$now-120) unset($state['nonces'][$k]);
            $state['nonces'][$nonce]=array('digest'=>$digest,'ts'=>$p['ts']);
            if($action==='status') {
                return array('site'=>$this->cfg['site'],'enforcement_enabled'=>$this->cfg['enforcement_enabled']===true,'remote_addr'=>$server['REMOTE_ADDR']??null,
                  'forwarding_headers_present'=>array_values(array_filter(array('HTTP_X_FORWARDED_FOR','HTTP_X_REAL_IP','HTTP_CF_CONNECTING_IP','HTTP_FORWARDED'),function($k)use($server){return isset($server[$k]);})),
                  'server_software'=>$server['SERVER_SOFTWARE']??null,'htaccess_sha256'=>is_file($this->cfg['root'].'/.htaccess')?hash_file('sha256',$this->cfg['root'].'/.htaccess'):null);
            }
            if($this->cfg['enforcement_enabled']!==true) throw new RuntimeException('enforcement_disabled');
            $ip=self::ip($p['ip']??'');if($this->protectedIP($ip)) throw new RuntimeException('protected_ip');
            $id=$p['decision_id']??'';if(!preg_match('/^[A-Za-z0-9_-]{16,96}$/D',$id)) throw new RuntimeException('invalid_decision_id');
            $existing=$state['decisions'][$id]??null;
            if($existing && $existing['ip']!==$ip) throw new RuntimeException('decision_owner_conflict');
            if($action==='block') {
                if(!$existing) $state['decisions'][$id]=array('ip'=>$ip,'active'=>true,'created'=>$now);
            } else $state['decisions'][$id]=array('ip'=>$ip,'active'=>false,'cancelled'=>$now);
            // Persist desired state first. A failed/crashed render is reconciled by retry.
            $this->audit(array('action'=>$action,'decision_id'=>$id,'ip'=>$ip,'phase'=>'desired'));
            self::atomic($path,json_encode($state));
            $hash=$this->reconcile($state,$beforeRename);
            $this->audit(array('action'=>$action,'decision_id'=>$id,'ip'=>$ip,'phase'=>'applied','hash'=>$hash));
            return array('decision_id'=>$id,'ip'=>$ip,'active'=>$state['decisions'][$id]['active'],'htaccess_sha256'=>$hash);
        } finally {flock($lock,LOCK_UN);fclose($lock);}
    }
}
