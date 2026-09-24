<?php
class EADEntry {
    public static function record($private,$server,$raw,$now=null) {
        $now=$now??microtime(true);
        if(($server['REQUEST_METHOD']??'')!=='POST') throw new RuntimeException('method');
        if(empty($server['HTTPS']) || $server['HTTPS']==='off') throw new RuntimeException('tls');
        if(($server['HTTP_ORIGIN']??'')!=='https://modirankhodro-emdad.com') throw new RuntimeException('origin');
        if(strlen($raw)>1024) throw new RuntimeException('size');
        $p=json_decode($raw,true);
        if(!is_array($p) || array_diff(array_keys($p),array('gclid','navigation_type','utm_campaign')) || ($p['navigation_type']??'')!=='navigate' || !is_string($p['gclid']??null) || !preg_match('/^[A-Za-z0-9_-]{20,256}$/D',$p['gclid'])) throw new RuntimeException('payload');
        if(isset($p['utm_campaign']) && (!is_string($p['utm_campaign']) || strlen($p['utm_campaign'])>200)) throw new RuntimeException('utm_campaign');
        $peer=$server['REMOTE_ADDR']??'';
        if(!filter_var($peer,FILTER_VALIDATE_IP,FILTER_FLAG_NO_PRIV_RANGE|FILTER_FLAG_NO_RES_RANGE)) throw new RuntimeException('peer');
        $ip=inet_ntop(inet_pton($peer));
        $lock=fopen($private.'/entries.lock','c');if(!$lock || !flock($lock,LOCK_EX)) throw new RuntimeException('lock');
        try {
            $path=$private.'/entries.json';$s=is_file($path)?json_decode(file_get_contents($path),true):array('last_id'=>0,'entries'=>array(),'rates'=>array());
            if(!is_array($s) || !isset($s['last_id'],$s['entries'],$s['rates'])) throw new RuntimeException('state');
            // Rate map is separately bounded; journal rotation cannot reset a busy IP.
            foreach($s['rates'] as $key=>$times) {$s['rates'][$key]=array_values(array_filter($times,function($t)use($now){return $t>$now-60;}));if(!$s['rates'][$key])unset($s['rates'][$key]);}
            $times=$s['rates'][$ip]??array();if(count($times)>=10) throw new RuntimeException('rate');
            if(!isset($s['rates'][$ip]) && count($s['rates'])>=1000) throw new RuntimeException('capacity');
            $times[]=$now;$s['rates'][$ip]=$times;
            $s['last_id']++;$s['entries'][]=array('id'=>$s['last_id'],'ip_address'=>$ip,'gclid'=>$p['gclid'],'received_at'=>$now,'utm_campaign'=>$p['utm_campaign']??'');
            $s['entries']=array_slice($s['entries'],-1000);
            EADAccess::atomic($path,json_encode($s));
            return array('accepted'=>true);
        } finally {flock($lock,LOCK_UN);fclose($lock);}
    }
    public static function read($private,$since=null) {
        $lock=fopen($private.'/entries.lock','c');if(!$lock || !flock($lock,LOCK_SH)) throw new RuntimeException('lock');
        try {
            $path=$private.'/entries.json';$s=is_file($path)?json_decode(file_get_contents($path),true):array('last_id'=>0,'entries'=>array());
            if(!is_array($s) || !isset($s['last_id'],$s['entries'])) throw new RuntimeException('entry_state');
            return array('site'=>'modirankhodro-emdad.com','last_id'=>$s['last_id'],'entries'=>$since===null?array():array_values(array_filter($s['entries'],function($e)use($since){return $e['id']>$since;})));
        } finally {flock($lock,LOCK_UN);fclose($lock);}
    }
}
